import uuid
import decimal
import stripe
from django.conf import settings
from django.db import transaction
from django.urls import reverse
from core.models import Wallet, Transaction


class WalletService:

    @staticmethod
    def get_or_create_wallet(user):
        """Get or create a wallet for a user, generating a wallet number if new."""
        wallet, created = Wallet.objects.get_or_create(user=user)
        if created and not wallet.wallet_number:
            wallet.wallet_number = str(uuid.uuid4()).replace('-', '')[:16].upper()
            wallet.save()
        return wallet, created

    @staticmethod
    def toggle_balance_privacy(user):
        """Toggle the balance hidden state for a user's wallet."""
        wallet = getattr(user, 'wallet', None)
        if wallet:
            wallet.is_hidden = not wallet.is_hidden
            wallet.save()
            return wallet
        return None

    @staticmethod
    def withdraw(wallet, amount, bank_name, account_number):
        """Deduct from wallet balance and create a withdrawal transaction."""
        from core.services import NotificationService
        with transaction.atomic():
            wallet.balance -= decimal.Decimal(amount)
            wallet.save()

            Transaction.objects.create(
                wallet=wallet,
                amount=amount,
                direction='debit',
                transaction_type='withdrawal',
                status='pending',
                description=f"Withdrawal to {bank_name} ({account_number})",
                reference_id=str(uuid.uuid4()).replace('-', '')[:12].upper()
            )

            NotificationService.create_notification(
                recipient=wallet.user,
                notification_type='withdrawal_processed',
                title='Withdrawal Requested',
                message=f"Your withdrawal request of RM{amount} to {bank_name} has been received and is pending.",
                link=reverse('client_wallet') if hasattr(wallet.user, 'client') else reverse('freelancer_wallet')
            )

    @staticmethod
    def create_topup_transaction(user, amount):
        """Create a pending top-up transaction and return it."""
        with transaction.atomic():
            wallet, created = WalletService.get_or_create_wallet(user)
            reference_id = str(uuid.uuid4()).replace('-', '')[:12].upper()
            txn = Transaction.objects.create(
                wallet=wallet,
                amount=amount,
                direction='credit',
                transaction_type='top_up',
                status='pending',
                description="Wallet Top Up via Stripe",
                reference_id=reference_id
            )
        return txn

    @staticmethod
    def complete_topup(reference_id):
        """Complete a pending top-up transaction and credit the wallet."""
        from core.services import NotificationService
        try:
            txn = Transaction.objects.get(reference_id=reference_id, status='pending')
            with transaction.atomic():
                txn.status = 'completed'
                txn.save()
                wallet = txn.wallet
                wallet.balance += txn.amount
                wallet.save()

                NotificationService.create_notification(
                    recipient=wallet.user,
                    notification_type='topup_success',
                    title='Top-up Successful',
                    message=f"RM{txn.amount} has been added to your wallet successfully.",
                    link=reverse('client_wallet') if hasattr(wallet.user, 'client') else reverse('freelancer_wallet')
                )
            return True, txn
        except Transaction.DoesNotExist:
            return False, None

    @staticmethod
    def cancel_topup(transaction_id, user):
        """Cancel a pending top-up transaction."""
        from core.services import NotificationService
        wallet = getattr(user, 'wallet', None)
        if not wallet:
            return False
        try:
            txn = Transaction.objects.get(id=transaction_id, wallet=wallet, status='pending', transaction_type='top_up')
            txn.status = 'cancelled'
            txn.save()

            NotificationService.create_notification(
                recipient=user,
                notification_type='topup_cancelled',
                title='Top-up Cancelled',
                message=f"Your wallet top-up of RM{txn.amount} was cancelled.",
                link=reverse('client_wallet') if hasattr(user, 'client') else reverse('freelancer_wallet')
            )
            return True
        except Transaction.DoesNotExist:
            return False


class PaymentService:

    @staticmethod
    def create_stripe_checkout_session(request, txn):
        """Create a Stripe Checkout Session for a top-up transaction."""
        stripe.api_key = settings.STRIPE_SECRET_KEY
        domain_url = request.build_absolute_uri('/')[:-1]
        session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price_data': {
                    'currency': 'myr',
                    'product_data': {
                        'name': 'Wallet Top Up',
                        'description': 'Add funds to your TalentSync Wallet',
                    },
                    'unit_amount': int(txn.amount * 100),
                },
                'quantity': 1,
            }],
            mode='payment',
            success_url=domain_url + reverse('payment_success') + '?session_id={CHECKOUT_SESSION_ID}',
            cancel_url=domain_url + reverse('payment_cancel'),
            client_reference_id=txn.reference_id,
        )
        return session

    @staticmethod
    def verify_stripe_payment(session_id):
        """Verify a Stripe payment and return the reference_id if paid."""
        stripe.api_key = settings.STRIPE_SECRET_KEY
        session = stripe.checkout.Session.retrieve(session_id)
        if session.payment_status == 'paid':
            return session.get('client_reference_id')
        return None
