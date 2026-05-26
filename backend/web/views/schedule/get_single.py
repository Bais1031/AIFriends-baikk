from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from web.models.schedule import Schedule


class GetSingleScheduleView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            schedule_id = request.query_params.get('schedule_id')
            schedule = Schedule.objects.filter(id=schedule_id, user__user=request.user).first()
            if not schedule:
                return Response({'result': '日程不存在'})

            return Response({
                'result': 'success',
                'schedule': {
                    'id': schedule.id,
                    'title': schedule.title,
                    'description': schedule.description,
                    'start_time': schedule.start_time.isoformat(),
                    'end_time': schedule.end_time.isoformat() if schedule.end_time else None,
                    'location': schedule.location,
                    'repeat_type': schedule.repeat_type,
                    'reminder_before': schedule.reminder_before,
                    'source': schedule.source,
                    'status': schedule.status,
                },
            })
        except:
            return Response({'result': '系统异常，请稍后重试'})
