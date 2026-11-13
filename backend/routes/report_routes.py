from flask import Blueprint, jsonify, Response
from services.report_service import ReportService
from services.notifier import get_live_feed

report_bp = Blueprint('report_bp', __name__)


@report_bp.get('/api/reports/compliance')
def get_compliance():
    summary = ReportService.get_compliance_summary()
    return jsonify(summary)


@report_bp.get('/api/reports/audit.csv')
def export_audit_csv():
    csv_content = ReportService.generate_csv_audit_log()
    return Response(
        csv_content,
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment; filename=sanitrack_audit_report.csv'}
    )


@report_bp.get('/api/notifications/live')
def live_notifications():
    feed = get_live_feed()
    return jsonify({'feed': feed})

