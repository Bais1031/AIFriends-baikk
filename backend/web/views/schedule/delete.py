from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from web.models.schedule import Schedule


class DeleteScheduleView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            schedule_id = request.data.get('schedule_id')
            deleted = Schedule.objects.filter(id=schedule_id, user__user=request.user).delete()[0]
            if deleted == 0:
                return Response({'result': '日程不存在'})
            return Response({'result': 'success'})
        except:
            return Response({'result': '系统异常，请稍后重试'})
