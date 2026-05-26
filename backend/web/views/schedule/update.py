from django.utils.dateparse import parse_datetime
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from web.models.schedule import Schedule


class UpdateScheduleView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            schedule_id = request.data.get('schedule_id')
            schedule = Schedule.objects.filter(id=schedule_id, user__user=request.user).first()
            if not schedule:
                return Response({'result': '日程不存在'})

            if 'title' in request.data:
                schedule.title = request.data['title'].strip()
            if 'description' in request.data:
                schedule.description = request.data['description']
            if 'start_time' in request.data:
                st = parse_datetime(request.data['start_time'])
                if st:
                    schedule.start_time = st
            if 'end_time' in request.data:
                et = request.data['end_time']
                schedule.end_time = parse_datetime(et) if et else None
            if 'location' in request.data:
                schedule.location = request.data['location']
            if 'repeat_type' in request.data:
                schedule.repeat_type = request.data['repeat_type']
            if 'reminder_before' in request.data:
                schedule.reminder_before = int(request.data['reminder_before'])
            if 'status' in request.data:
                schedule.status = request.data['status']

            schedule.save()
            return Response({'result': 'success'})
        except:
            return Response({'result': '系统异常，请稍后重试'})
