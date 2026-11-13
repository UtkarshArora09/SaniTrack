import threading
import time
import logging
from datetime import datetime, timezone, timedelta
from database import fetch_all, execute, utc_now_iso

logger = logging.getLogger('SaniTrack.Scheduler')


class ShiftMonitoringDaemon:
    """
    Automated shift and absence tracking daemon.
    Checks shift timings against actual attendance records and dispatches alerts automatically.
    """
    def __init__(self, notify_fn, check_interval_seconds=60, grace_period_minutes=15):
        self.notify = notify_fn
        self.interval = check_interval_seconds
        self.grace_period = grace_period_minutes
        self.running = False
        self.thread = None
        self._alerted_shifts_today = set()  # (date_str, shift_id)

    def start(self):
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._run_loop, daemon=True, name='ShiftDaemon')
        self.thread.start()
        logger.info('Automated Shift Monitoring Daemon started.')

    def stop(self):
        self.running = False

    def _run_loop(self):
        while self.running:
            try:
                self.check_shifts()
            except Exception as e:
                logger.error(f'Error during shift check: {e}', exc_info=True)

            for _ in range(self.interval):
                if not self.running:
                    break
                time.sleep(1)

    def check_shifts(self):
        now = datetime.now()
        today_str = now.strftime('%Y-%m-%d')
        current_time_str = now.strftime('%H:%M')

        active_shifts = fetch_all(
            '''SELECT s.*, w.name AS ward_name, e.name AS employee_name, e.phone AS employee_phone, e.telegram_chat_id AS employee_chat_id
               FROM shift_schedules s
               JOIN wards w ON w.name = s.ward_name
               LEFT JOIN employees e ON e.emp_key = s.assigned_employee_key
               WHERE s.is_active = 1 AND s.assigned_employee_key IS NOT NULL'''
        )


        for shift in active_shifts:
            shift_id = shift['id']
            ward_name = shift['ward_name']
            emp_key = shift['assigned_employee_key']
            emp_name = shift.get('employee_name') or emp_key
            start_str = shift['start_time']
            end_str = shift['end_time']

            alert_key = (today_str, shift_id)
            if alert_key in self._alerted_shifts_today:
                continue

            try:
                start_dt = datetime.strptime(f'{today_str} {start_str}', '%Y-%m-%d %H:%M')
                grace_deadline = start_dt + timedelta(minutes=self.grace_period)

                # Check if current time has passed start_time + grace_period
                if now > grace_deadline:
                    # Check if worker has logged attendance for this ward today
                    today_start_iso = f'{today_str}T00:00:00'
                    attendance = fetch_all(
                        '''SELECT id FROM attendance_logs 
                           WHERE ward_name = ? AND employee_key = ? AND created_at >= ?''',
                        (ward_name, emp_key, today_start_iso)
                    )

                    if not attendance:
                        # Worker is absent!
                        msg = (f"Automated Absence Alert: {emp_name} is absent for {ward_name} "
                               f"during {shift['shift_name']} (started at {start_str}).")
                        logger.warning(msg)
                        self.notify(
                            ward_name,
                            msg,
                            employee_phone=shift.get('employee_phone'),
                            employee_chat_id=shift.get('employee_chat_id')
                        )
                        self._alerted_shifts_today.add(alert_key)

            except Exception as parse_err:
                logger.error(f"Error parsing shift time for shift {shift_id}: {parse_err}")

