from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from web.models.agent_conversation import AgentConversation


class AgentClearHistoryView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user_profile = request.user.userprofile
        deleted, _ = AgentConversation.objects.filter(user=user_profile).delete()
        return Response({
            'result': 'success',
            'deleted': deleted,
        })
