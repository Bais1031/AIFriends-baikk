from django.utils.dateparse import parse_datetime
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from web.models.schedule import Schedule
from web.models.user import UserProfile


class CreateScheduleView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            user_profile = UserProfile.objects.get(user=request.user)
            title = request.data.get('title', '').strip()
            start_time = request.data.get('start_time')
            if not title or not start_time:
                return Response({'result': '标题和开始时间不能为空'})

            start_time = parse_datetime(start_time)
            if not start_time:
                return Response({'result': '时间格式不正确'})

            end_time = parse_datetime(request.data.get('end_time', '')) if request.data.get('end_time') else None

            schedule = Schedule.objects.create(
                user=user_profile,
                title=title,
                description=request.data.get('description', ''),
                start_time=start_time,
                end_time=end_time,
                location=request.data.get('location', ''),
                repeat_type=request.data.get('repeat_type', 'none'),
                reminder_before=int(request.data.get('reminder_before', 30)),
                source=request.data.get('source', 'text'),
            )
            return Response({
                'result': 'success',
                'schedule': self._serialize(schedule),
            })
        except:
            return Response({'result': '系统异常，请稍后重试'})

    def _serialize(self, s):
        return {
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
        }
