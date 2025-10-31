# Import modules
import gzip
import json
import os
import sys
import time

import requests

# Build data to send with requests
ORG_ID = os.getenv('ORG_ID')
CIRCLECI_TOKEN = os.getenv('CIRCLECI_API_TOKEN')
START_DATE = os.getenv('START_DATE')
END_DATE = os.getenv('END_DATE')

post_data = {
    "start": f"{START_DATE}T00:00:01Z",
    "end": f"{END_DATE}T00:00:01Z",
    "shared_org_ids": []
}

# Request the usage report
response = requests.post(
    f"https://circleci.com/api/v2/organizations/{ORG_ID}/usage_export_job",
    headers={"Circle-Token": CIRCLECI_TOKEN, "Content-Type": "application/json"},
    data=json.dumps(post_data)
)
# Print out the API response for the usage report request
print("Response Content:", response.json())  # This will parse the JSON response

# Once requested, the report can take some time to process, so a retry is built-in
if response.status_code == 201:
    print("Report requested successfully")
    data = response.json()
    USAGE_REPORT_ID = data.get("usage_export_job_id")
    print(f"Report ID is {USAGE_REPORT_ID}")
  
    # Check if the report is ready for downloading as it can take a while to process
    for i in range(5):
        print("Checking if report can be downloaded")
        report = requests.get(
            f"https://circleci.com/api/v2/organizations/{ORG_ID}/usage_export_job/{USAGE_REPORT_ID}",
            headers={"Circle-Token": CIRCLECI_TOKEN}
        ).json()

        report_status = report.get("state")

        # Download the report and save it
        if report_status == "completed":
            print("Report generated. Now Downloading...")
            download_urls = report.get("download_urls", [])

            os.makedirs("/tmp/reports", exist_ok=True)

            for idx, url in enumerate(download_urls):
                r = requests.get(url)
                with open(f"/tmp/usage_report_{idx}.csv.gz", "wb") as f:
                    f.write(r.content)             
                with gzip.open(f"/tmp/usage_report_{idx}.csv.gz", "rb") as f_in:
                    with open(f"/tmp/reports/usage_report_{idx}.csv", "wb") as f_out:
                        f_out.write(f_in.read())

                print(f"File {idx} downloaded and extracted")

            print("All files downloaded and extracted to the /reports directory")
            break      
        elif report_status == "processing":
            print("Report still processing. Retrying in 1 minute...")
            time.sleep(60)  # Wait for 60 seconds before retrying       
        else:
            print(f"Report status: {report_status}. Error occurred.")
            break
    else:
        print("Report is still in processing state after 5 retries.")
        sys.exit(1)
else:
    # Exit if something else happens, like requests are being throttled
    print(f"{response}")
    sys.exit(1)
