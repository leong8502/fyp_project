"""
Chat views – conversation list, message API, send/download, mute.
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, FileResponse, Http404
from django.urls import reverse
from django.contrib import messages

from core.models import Conversation, ChatParticipant, Message


@login_required
def chat_view(request):
    context = {}
    if hasattr(request.user, 'client'):
        context['base_template'] = 'core/client_master.html'
        context['find_url'] = 'client_search'
        context['find_text'] = 'Find Freelancers'
        context['dashboard_url'] = 'client_home'
    elif hasattr(request.user, 'freelancer'):
        context['base_template'] = 'core/freelancer_master.html'
        context['find_url'] = 'freelancer_home'
        context['find_text'] = 'Find Jobs'
        context['dashboard_url'] = 'freelancer_home'
    else:
        context['base_template'] = 'core/master.html'
        context['find_url'] = 'home'
        context['find_text'] = 'Go Home'

    return render(request, 'core/chat.html', context)


@login_required
def start_chat(request, user_id):
    from django.contrib.auth.models import User
    other_user = get_object_or_404(User, id=user_id)
    if other_user == request.user:
        messages.error(request, "You cannot chat with yourself.")
        return redirect('client_search')

    my_convs = Conversation.objects.filter(participants=request.user)
    common_convs = my_convs.filter(participants=other_user).distinct()

    if common_convs.exists():
        conversation = common_convs.first()
        # Reset is_removed for the current user if they are starting the chat again
        ChatParticipant.objects.filter(user=request.user, conversation=conversation).update(is_removed=False)
    else:
        conversation = Conversation.objects.create()
        ChatParticipant.objects.create(user=request.user, conversation=conversation)
        ChatParticipant.objects.create(user=other_user, conversation=conversation)

    return redirect(reverse('chat') + f'?conversation_id={conversation.id}')


@login_required
def api_get_conversations(request):
    participants = ChatParticipant.objects.filter(user=request.user, is_removed=False).select_related('conversation')
    data = []

    for p in participants:
        conv = p.conversation
        other_participant = conv.participants.exclude(id=request.user.id).first()
        if not other_participant:
            continue

        last_message = conv.messages.last()
        unread_count = conv.messages.filter(is_read=False).exclude(sender=request.user).count()

        name = other_participant.username
        avatar_url = '/static/core/images/default_profile.png'
        role = ''
        tagline = ''

        if hasattr(other_participant, 'client'):
            name = other_participant.client.company_name or other_participant.username
            role = 'Client'
            tagline = other_participant.client.tagline or ''
            if other_participant.client.profile_image:
                avatar_url = other_participant.client.profile_image.url
        elif hasattr(other_participant, 'freelancer'):
            name = other_participant.freelancer.full_name or other_participant.username
            role = 'Freelancer'
            tagline = other_participant.freelancer.tagline or ''
            if other_participant.freelancer.profile_image:
                avatar_url = other_participant.freelancer.profile_image.url

        last_msg_preview = ''
        if last_message:
            if last_message.attachment:
                if last_message.attachment_type == 'image':
                    last_msg_preview = "📷 Photo"
                else:
                    filename = last_message.original_filename or last_message.attachment.name.split('/')[-1]
                    last_msg_preview = f'<i class="fas fa-paperclip"></i> {filename}'
            else:
                last_msg_preview = last_message.content

        data.append({
            'id': conv.id,
            'other_user_id': other_participant.id,
            'name': name,
            'avatar': avatar_url,
            'role': role,
            'tagline': tagline,
            'last_message': last_msg_preview,
            'last_message_time': last_message.created_at.isoformat() if last_message else conv.created_at.isoformat(),
            'is_muted': p.is_muted,
            'unread_count': unread_count,
        })

    data.sort(key=lambda x: x['last_message_time'], reverse=True)
    return JsonResponse(data, safe=False)


@login_required
def api_get_messages(request, conversation_id):
    conversation = get_object_or_404(Conversation, id=conversation_id)
    if not conversation.participants.filter(id=request.user.id).exists():
        return JsonResponse({'error': 'Unauthorized'}, status=403)

    conversation.messages.filter(is_read=False).exclude(sender=request.user).update(is_read=True)

    data = []
    for msg in conversation.messages.select_related('sender').all():
        sender_name = "Me"
        if msg.sender != request.user:
            if hasattr(msg.sender, 'client'):
                sender_name = msg.sender.client.company_name
            elif hasattr(msg.sender, 'freelancer'):
                sender_name = msg.sender.freelancer.full_name

        sender_avatar = '/static/core/images/default_profile.png'
        if hasattr(msg.sender, 'client') and msg.sender.client.profile_image:
            sender_avatar = msg.sender.client.profile_image.url
        elif hasattr(msg.sender, 'freelancer') and msg.sender.freelancer.profile_image:
            sender_avatar = msg.sender.freelancer.profile_image.url

        data.append({
            'id': msg.id,
            'sender_id': msg.sender.id,
            'is_me': msg.sender == request.user,
            'sender_name': sender_name,
            'sender_avatar': sender_avatar,
            'content': msg.content,
            'attachment': msg.attachment.url if msg.attachment else None,
            'original_filename': msg.original_filename,
            'attachment_type': msg.attachment_type,
            'attachment_size': msg.attachment_size,
            'created_at': msg.created_at.isoformat(),
            'is_read': msg.is_read,
        })

    return JsonResponse(data, safe=False)


@login_required
def api_download_attachment(request, message_id):
    message = get_object_or_404(Message, id=message_id)
    if not message.attachment:
        raise Http404("No attachment")
    if not message.conversation.participants.filter(id=request.user.id).exists():
        return JsonResponse({'error': 'Unauthorized'}, status=403)

    filename = message.original_filename or message.attachment.name.split('/')[-1]
    try:
        response = FileResponse(message.attachment.open('rb'))
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response
    except FileNotFoundError:
        raise Http404("File not found")


@login_required
def api_send_message(request, conversation_id):
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    try:
        conversation = get_object_or_404(Conversation, id=conversation_id)
        if not conversation.participants.filter(id=request.user.id).exists():
            return JsonResponse({'error': 'Unauthorized'}, status=403)

        content = request.POST.get('content', '')
        attachment = request.FILES.get('attachment')

        if not content and not attachment:
            return JsonResponse({'error': 'Content or attachment is required'}, status=400)

        attachment_type = None
        attachment_size = None
        original_filename = None

        if attachment:
            original_filename = attachment.name
            if attachment.size > 10 * 1024 * 1024:
                return JsonResponse({'error': 'File size exceeds 10MB limit'}, status=400)

            file_ext = attachment.name.split('.')[-1].lower()
            if file_ext in ['jpg', 'jpeg', 'png', 'gif', 'webp']:
                attachment_type = 'image'
            elif file_ext == 'pdf':
                attachment_type = 'pdf'
            elif file_ext in ['doc', 'docx', 'txt', 'zip']:
                attachment_type = 'document'
            else:
                return JsonResponse({'error': 'Unsupported file type'}, status=400)

            attachment_size = attachment.size

        # Mark existing messages as read for the sender
        Message.objects.filter(
            conversation=conversation, 
            is_read=False
        ).exclude(sender=request.user).update(is_read=True)

        message = Message.objects.create(
            conversation=conversation,
            sender=request.user,
            content=content,
            attachment=attachment,
            original_filename=original_filename,
            attachment_type=attachment_type,
            attachment_size=attachment_size,
        )

        # Reset is_removed for ALL participants when a new message is sent
        # (This ensures the conversation reappears in their lists)
        conversation.chatparticipant_set.update(is_removed=False)
        conversation.save()

        sender_name = "Me"
        if hasattr(request.user, 'client'):
            sender_name = request.user.client.company_name
        elif hasattr(request.user, 'freelancer'):
            sender_name = request.user.freelancer.full_name

        sender_avatar = '/static/core/images/default_profile.png'
        if hasattr(request.user, 'client') and request.user.client.profile_image:
            sender_avatar = request.user.client.profile_image.url
        elif hasattr(request.user, 'freelancer') and request.user.freelancer.profile_image:
            sender_avatar = request.user.freelancer.profile_image.url

        message_data = {
            'id': message.id,
            'sender_id': request.user.id,
            'sender_name': sender_name,
            'sender_avatar': sender_avatar,
            'content': message.content,
            'attachment': message.attachment.url if message.attachment else None,
            'original_filename': message.original_filename,
            'attachment_type': message.attachment_type,
            'attachment_size': message.attachment_size,
            'created_at': message.created_at.isoformat(),
            'is_read': message.is_read,
        }

        from channels.layers import get_channel_layer
        from asgiref.sync import async_to_sync
        channel_layer = get_channel_layer()

        async_to_sync(channel_layer.group_send)(
            f'chat_{conversation_id}',
            {'type': 'chat_message', 'message': message_data}
        )

        for participant in conversation.participants.all():
            async_to_sync(channel_layer.group_send)(
                f'user_{participant.id}',
                {'type': 'conversation_updated'}
            )

        return JsonResponse({'status': 'success', 'message_id': message.id, 'message': message_data})

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


@login_required
def api_toggle_mute(request, conversation_id):
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    participant = get_object_or_404(ChatParticipant, conversation_id=conversation_id, user=request.user)
    participant.is_muted = not participant.is_muted
    participant.save()
    return JsonResponse({'status': 'success', 'is_muted': participant.is_muted})


@login_required
def api_remove_chat(request, conversation_id):
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    participant = get_object_or_404(ChatParticipant, conversation_id=conversation_id, user=request.user)
    participant.is_removed = True
    participant.save()
    return JsonResponse({'status': 'success'})
