import csv
import io
from database import fetch_all, fetch_one


class ReportService:
    @staticmethod
    def get_compliance_summary():
        total_inspections = fetch_one("SELECT COUNT(*) as count FROM inspection_logs")['count']
        clean_inspections = fetch_one(
            "SELECT COUNT(*) as count FROM inspection_logs WHERE COALESCE(overridden_status, status) = 'Clean'"
        )['count']
        not_clean_inspections = fetch_one(
            "SELECT COUNT(*) as count FROM inspection_logs WHERE COALESCE(overridden_status, status) = 'Not Clean'"
        )['count']
        overrides = fetch_one("SELECT COUNT(*) as count FROM inspection_logs WHERE overridden_status IS NOT NULL")['count']

        total_attendance = fetch_one("SELECT COUNT(*) as count FROM attendance_logs")['count']
        valid_attendance = fetch_one("SELECT COUNT(*) as count FROM attendance_logs WHERE assigned_match = 1")['count']
        mismatches = fetch_one("SELECT COUNT(*) as count FROM attendance_logs WHERE assigned_match = 0")['count']

        hygiene_compliance_pct = round((clean_inspections / total_inspections * 100), 1) if total_inspections > 0 else 100.0
        attendance_compliance_pct = round((valid_attendance / total_attendance * 100), 1) if total_attendance > 0 else 100.0

        ward_scorecards = fetch_all('''
            SELECT w.name as ward_name,
                   w.location,
                   e.name as assigned_worker,
                   COUNT(i.id) as total_inspections,
                   SUM(CASE WHEN COALESCE(i.overridden_status, i.status) = 'Clean' THEN 1 ELSE 0 END) as clean_count,
                   SUM(CASE WHEN COALESCE(i.overridden_status, i.status) = 'Not Clean' THEN 1 ELSE 0 END) as not_clean_count,
                   MAX(i.created_at) as last_inspected_at
            FROM wards w
            LEFT JOIN employees e ON e.emp_key = w.assigned_employee_key
            LEFT JOIN inspection_logs i ON i.ward_name = w.name
            GROUP BY w.name, w.location, e.name
            ORDER BY w.name
        ''')

        for item in ward_scorecards:
            tot = item['total_inspections'] or 0
            cln = item['clean_count'] or 0
            item['compliance_rate'] = round((cln / tot * 100), 1) if tot > 0 else 100.0

        return {
            'hygiene_compliance_pct': hygiene_compliance_pct,
            'attendance_compliance_pct': attendance_compliance_pct,
            'total_inspections': total_inspections,
            'clean_inspections': clean_inspections,
            'not_clean_inspections': not_clean_inspections,
            'supervisor_overrides': overrides,
            'total_attendance_logs': total_attendance,
            'attendance_mismatches': mismatches,
            'ward_scorecards': ward_scorecards
        }

    @staticmethod
    def generate_csv_audit_log():
        """Generates an audit CSV string containing the complete history of inspections and overrides."""
        rows = fetch_all('''
            SELECT i.id,
                   i.ward_name,
                   i.employee_key,
                   i.status as raw_model_status,
                   COALESCE(i.overridden_status, i.status) as final_status,
                   i.object_found,
                   i.confidence,
                   i.object_count,
                   i.raw_label,
                   i.overridden_by,
                   i.override_reason,
                   i.overridden_at,
                   i.notes,
                   i.created_at
            FROM inspection_logs i
            ORDER BY i.created_at DESC
        ''')

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            'Inspection ID', 'Ward Name', 'Employee Key', 'Raw Model Status', 'Final Status',
            'Waste Detected', 'Confidence', 'Object Count', 'Primary Class', 'Overridden By',
            'Override Reason', 'Overridden At', 'Notes', 'Timestamp UTC'
        ])

        for r in rows:
            writer.writerow([
                r['id'],
                r['ward_name'],
                r['employee_key'] or 'Unassigned',
                r['raw_model_status'],
                r['final_status'],
                'Yes' if r['object_found'] else 'No',
                f"{r['confidence']:.4f}" if r['confidence'] else 'N/A',
                r['object_count'],
                r['raw_label'] or 'None',
                r['overridden_by'] or 'None',
                r['override_reason'] or 'N/A',
                r['overridden_at'] or 'N/A',
                r['notes'] or '',
                r['created_at']
            ])

        return output.getvalue()

