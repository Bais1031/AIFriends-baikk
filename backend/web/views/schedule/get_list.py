from datetime import datetime
from django.utils.dateparse import parse_datetime
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from web.models.schedule import Schedule


class GetListScheduleView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            year = int(request.query_params.get('year', datetime.now().year))
            month = int(request.query_params.get('month', datetime.now().month))

            schedules = Schedule.objects.filter(
                user__user=request.user,
                start_time__year=year,
                start_time__month=month,
            )

            result = []
            for s in schedules:
                result.append({
                    'id': s.id,
                    'title': s.title,
                    'description': s.description,
                    'start_time': s.start_time.isoformat(),
                    'end_time': s.end_time.isoformat() if s.end_time else None,
                    'location': s.location,
                    'repeat_type': s.repeat_type,
                    'reminder_before': s.reminder_before,
                    'source': s.source,
                    'status': s.status,
                })

            return Response({
                'result': 'success',
                'schedules': result,
            })
        except:
            return Response({'result': '系统异常，请稍后重试'})
