import time
import requests
import random

BASE_URL = 'http://127.0.0.1:5000'
WARDS = ['Emergency', 'ICU', 'Ward 1', 'Ward 2', 'Pediatrics']


def run_cctv_simulation(cycles=5, interval=10):
    print('=' * 60)
    print('SaniTrack Continuous CCTV Feed Ingestion Simulator')
    print('=' * 60)

    for i in range(1, cycles + 1):
        target_ward = random.choice(WARDS)
        print(f"\n[Cycle {i}/{cycles}] Simulating CCTV video sweep for: {target_ward}...")

        try:
            # Trigger toggle or status check
            res = requests.get(f'{BASE_URL}/api/wards')
            if res.status_code == 200:
                print(f"  &bull; Ward list verified online ({len(res.json().get('wards', []))} wards active)")
            
            # Check compliance summary
            comp = requests.get(f'{BASE_URL}/api/reports/compliance').json()
            print(f"  &bull; Current Hospital Cleanliness Rate: {comp.get('hygiene_compliance_pct')}%")
            print(f"  &bull; Total Inspections Logged: {comp.get('total_inspections')}")

        except Exception as err:
            print(f"  &bull; Error communicating with SaniTrack API: {err}")

        time.sleep(interval)

    print("\nSimulation complete. Check the SaniTrack web dashboard for updated audit logs.")


if __name__ == '__main__':
    run_cctv_simulation()

