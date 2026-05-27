from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from web.models.agent_conversation import AgentConversation


class AgentHistoryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user_profile = request.user.userprofile

        history = AgentConversation.objects.filter(
            user=user_profile
        ).order_by('-create_time')[:50]
        history = list(reversed(history))

        messages = []
        for h in history:
            messages.append({
                'role': 'user' if h.role == 'human' else 'ai',
                'content': h.content,
            })

        return Response({
            'result': 'success',
            'messages': messages,
        })
