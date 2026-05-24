from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from web.models.friend import Friend, Message


class DeleteMessagesView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            friend_id = request.data.get('friend_id')
            message_ids = request.data.get('message_ids', [])

            if not message_ids:
                return Response({'result': '请选择要删除的消息'})

            friend = Friend.objects.filter(id=friend_id, me__user=request.user).first()
            if not friend:
                return Response({'result': '好友不存在'})

            deleted_count = Message.objects.filter(
                friend=friend, id__in=message_ids
            ).delete()[0]

            friend.conversation_summary = ''
            friend.summary_message_count = 0
            friend.save(update_fields=['conversation_summary', 'summary_message_count'])

            return Response({
                'result': 'success',
                'deleted_count': deleted_count,
            })
        except:
            return Response({'result': '系统异常，请稍后重试'})
