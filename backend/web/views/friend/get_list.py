from django.db.models import Q
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from web.models.friend import Friend, Message


class GetListFriendView(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request):
        try:
            items_count = int(request.query_params.get('items_count', 0))
            search_query = request.query_params.get('search_query', '').strip()

            queryset = Friend.objects.filter(me__user=request.user)
            if search_query:
                queryset = queryset.filter(
                    Q(character__name__icontains=search_query) |
                    Q(character__profile__icontains=search_query)
                )
            friends_raw = queryset.select_related(
                'character', 'character__author'
            ).order_by('-update_time')[items_count: items_count + 20]

            # 批量获取每个 friend 的最后一条消息
            friend_ids = [f.id for f in friends_raw]
            last_messages = {}
            for msg in Message.objects.filter(friend_id__in=friend_ids).order_by('friend_id', '-id'):
                if msg.friend_id not in last_messages:
                    last_messages[msg.friend_id] = msg

            friends = []
            for friend in friends_raw:
                character = friend.character
                author = character.author
                last_msg = last_messages.get(friend.id)
                if last_msg:
                    last_message_text = last_msg.output or last_msg.user_message or ''
                    last_message_time = last_msg.create_time.isoformat()
                else:
                    last_message_text = ''
                    last_message_time = ''

                friends.append({
                    'id': friend.id,
                    'character': {
                        'id': character.id,
                        'name': character.name,
                        'profile': character.profile,
                        'photo': character.photo.url,
                        'background_image': character.background_image.url,
                        'author': {
                            'user_id': author.user_id,
                            'username': author.user.username,
                            'photo': author.photo.url,
                        }
                    },
                    'last_message': last_message_text[:50],
                    'last_message_time': last_message_time,
                })
            return Response({
                'result': 'success',
                'friends': friends,
            })
        except:
            return Response({
                'result': '系统异常，请稍后重试'
            })