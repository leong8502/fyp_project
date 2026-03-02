"""
WebSocket consumers for real-time chat functionality
"""
import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth.models import User
from .models import Conversation, Message


class ChatConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for handling real-time chat messages
    """
    
    async def connect(self):
        """Handle WebSocket connection"""
        self.conversation_id = self.scope['url_route']['kwargs']['conversation_id']
        self.user = self.scope['user']
        self.user_group_name = f'user_{self.user.id}'
        self.room_group_name = None

        print(f"[WebSocket] User attempting to connect: {self.user}")
        
        # Check if user is authenticated
        if not self.user.is_authenticated:
            print(f"[WebSocket] REJECTED: User not authenticated")
            await self.close()
            return
        
        # Handle "global" connection (only user group, no specific conversation)
        if self.conversation_id == 'global':
            await self.channel_layer.group_add(
                self.user_group_name,
                self.channel_name
            )
            print(f"[WebSocket] ACCEPTED: User {self.user.username} connected to global channel")
            await self.accept()
            return

        # Regular conversation connection
        self.room_group_name = f'chat_{self.conversation_id}'
        
        # Verify user is participant in this conversation
        is_participant = await self.is_participant()
        print(f"[WebSocket] Is participant in conversation {self.conversation_id}: {is_participant}")
        
        if not is_participant:
            print(f"[WebSocket] REJECTED: User not a participant")
            await self.close()
            return
        
        # Join conversation-specific room group
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        
        # Join user-specific room group (for conversation list updates)
        await self.channel_layer.group_add(
            self.user_group_name,
            self.channel_name
        )
        
        print(f"[WebSocket] ACCEPTED: User {self.user.username} connected to conversation {self.conversation_id}")
        await self.accept()
        
        # Mark messages as read when user connects and notify for badge update
        await self.notify_mark_read()
    
    async def disconnect(self, close_code):
        """Handle WebSocket disconnection"""
        # Leave conversation room group
        if self.room_group_name:
            await self.channel_layer.group_discard(
                self.room_group_name,
                self.channel_name
            )
        
        # Leave user-specific room group
        if hasattr(self, 'user_group_name'):
            await self.channel_layer.group_discard(
                self.user_group_name,
                self.channel_name
            )
    
    async def receive(self, text_data):
        """Handle incoming WebSocket messages from client"""
        try:
            data = json.loads(text_data)
            message_type = data.get('type')
            
            if message_type == 'mark_read':
                # Mark messages as read and notify for badge update
                await self.notify_mark_read()
                
                # Notify other participants that messages were read (for UI receipts)
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'messages_read',
                        'user_id': self.user.id
                    }
                )
        except json.JSONDecodeError:
            pass

    async def notify_mark_read(self):
        """Mark messages as read and notify user group for badge update"""
        has_unread = await self._mark_messages_read_db()
        
        # Always broadcast to user group to ensure header badge stays sync
        await self.channel_layer.group_send(
            self.user_group_name,
            {
                'type': 'conversation_updated'
            }
        )
    
    async def chat_message(self, event):
        """Send chat message to WebSocket (called by group_send)"""
        await self.send(text_data=json.dumps({
            'type': 'chat_message',
            'message': event['message']
        }))
    
    async def messages_read(self, event):
        """Notify that messages were read by a user"""
        await self.send(text_data=json.dumps({
            'type': 'messages_read',
            'user_id': event['user_id']
        }))
    
    async def conversation_updated(self, event):
        """Notify that conversation list needs refresh"""
        await self.send(text_data=json.dumps({
            'type': 'conversation_updated'
        }))
    
    @database_sync_to_async
    def is_participant(self):
        """Check if user is a participant in this conversation"""
        try:
            conversation = Conversation.objects.get(id=self.conversation_id)
            return conversation.participants.filter(id=self.user.id).exists()
        except Conversation.DoesNotExist:
            return False

    @database_sync_to_async
    def _mark_messages_read_db(self):
        """Mark unread messages in database"""
        try:
            conversation = Conversation.objects.get(id=self.conversation_id)
            unread_qs = conversation.messages.filter(is_read=False).exclude(sender=self.user)
            has_unread = unread_qs.exists()
            if has_unread:
                unread_qs.update(is_read=True)
            return has_unread
        except Conversation.DoesNotExist:
            return False
