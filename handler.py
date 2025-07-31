import os
import glob

import src.get_usage_report
import src.send_to_datadog


SEND_TO_DATADOG = os.environ['SEND_TO_DATADOG']


def handler(event, context):
    src.get_usage_report.get_usage_report()
    print(os.getcwd())
    csv_files = glob.glob('/tmp/reports/*.{}'.format('csv'))
    if SEND_TO_DATADOG:
        if len(csv_files) > 0:
            for csv_file in csv_files:
                src.send_to_datadog.main(csv_file=csv_file)
        else:
            print("No CSV files found in /tmp/reports, skipping.")

    else:
        print("SEND_TO_DATADOG set to false, skipping.")
