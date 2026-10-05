from flask import Flask, render_template, jsonify, request, send_file
from flask_cors import CORS
import requests
from datetime import datetime, timedelta
from io import StringIO, BytesIO
import csv
import threading
import time

app = Flask(__name__)
CORS(app)

class CompaniesHouseTracker:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.company-information.service.gov.uk"
        self.results = []
        self.scan_status = "idle"
        self.progress = {}
        
        self.properties = {
            "City of London - EC1A": "EC1A",
            "City of London - EC1N": "EC1N",
            "City of London - EC1R": "EC1R",
            "City of London - EC1V": "EC1V",
            "City of London - EC2A": "EC2A",
            "City of London - EC2R": "EC2R",
            "City of London - EC2V": "EC2V",
            "City of London - EC2Y": "EC2Y",
            "City of London - EC3A": "EC3A",
            "City of London - EC3N": "EC3N",
            "City of London - EC3R": "EC3R",
            "City of London - EC3V": "EC3V",
            "City of London - EC4A": "EC4A",
            "City of London - EC4N": "EC4N",
            "City of London - EC4R": "EC4R",
            "City of London - EC4V": "EC4V",
            "West Central - WC1A": "WC1A",
            "West Central - WC1E": "WC1E",
            "West Central - WC1N": "WC1N",
            "West Central - WC1X": "WC1X",
            "West Central - WC2A": "WC2A",
            "West Central - WC2E": "WC2E",
            "West Central - WC2N": "WC2N",
            "West End - W1A": "W1A",
            "West End - W1C": "W1C",
            "West End - W1D": "W1D",
            "West End - W1F": "W1F",
            "West End - W1G": "W1G",
            "West End - W1H": "W1H",
            "West End - W1J": "W1J",
            "West End - W1K": "W1K",
            "West End - W1M": "W1M",
            "West End - W1T": "W1T",
            "West - W2": "W2",
            "Southwest - SW1A": "SW1A",
            "Southwest - SW1E": "SW1E",
            "Southwest - SW1H": "SW1H",
            "Southwest - SW1V": "SW1V",
            "Southwest - SW1W": "SW1W",
            "Southwest - SW1X": "SW1X",
            "Southwark - SE1": "SE1",
        }
    
    def search_companies_by_location(self, postcode: str):
        url = f"{self.base_url}/advanced-search/companies"
        all_companies = []
        start_index = 0

        while True:
            params = {
                "location": postcode,
                "company_status": "active",
                "size": 100,
                "start_index": start_index
            }

            try:
                response = requests.get(
                    url,
                    params=params,
                    auth=(self.api_key, ""),
                    timeout=10
                )
                response.raise_for_status()
                data = response.json()
                items = data.get("items", [])

                if not items:
                    break

                all_companies.extend(items)

                # Check if there are more results
                total_results = data.get("total_results", 0)
                if start_index + len(items) >= total_results:
                    break

                # Add delay between paginated requests to respect API limits
                time.sleep(0.5)
                start_index += 100
            except Exception as e:
                print(f"Error searching {postcode} at index {start_index}: {str(e)}")
                break

        return all_companies
    
    def get_filing_history(self, company_number: str, days_back: int = 90):
        url = f"{self.base_url}/company/{company_number}/filing-history"
        
        try:
            response = requests.get(
                url,
                auth=(self.api_key, ""),
                timeout=10
            )
            response.raise_for_status()
            
            filings = []
            cutoff_date = datetime.now() - timedelta(days=days_back)
            
            for filing in response.json().get("items", []):
                filing_date = datetime.strptime(filing.get("date", ""), "%Y-%m-%d")
                
                if filing.get("type") == "AD01" and filing_date >= cutoff_date:
                    filings.append({
                        "date": filing.get("date"),
                        "days_ago": (datetime.now() - filing_date).days
                    })
            
            return filings
        except Exception as e:
            return []
    
    def get_company_details(self, company_number: str):
        url = f"{self.base_url}/company/{company_number}"
        
        try:
            response = requests.get(
                url,
                auth=(self.api_key, ""),
                timeout=10
            )
            response.raise_for_status()
            data = response.json()
            
            return {
                "name": data.get("company_name"),
                "status": data.get("company_status"),
                "type": data.get("type"),
                "website": data.get("website"),
                "sic_codes": data.get("sic_codes", [])
            }
        except Exception as e:
            return {}
    
    def run_scan(self, progress_callback=None):
        self.results = []
        self.scan_status = "running"
        self.progress = {}
        total_postcodes = len(self.properties)

        for idx, (property_name, postcode) in enumerate(self.properties.items()):
            progress_data = {
                "status": "scanning",
                "current": idx + 1,
                "total": total_postcodes,
                "location": property_name,
                "results_found": len(self.results)
            }
            self.progress = progress_data

            if progress_callback:
                progress_callback(progress_data)
            
            companies = self.search_companies_by_location(postcode)

            # Add delay between postcode searches
            time.sleep(0.3)
            
            for company in companies:
                company_number = company.get("company_number")
                company_name = company.get("title")
                
                filings = self.get_filing_history(company_number)
                
                if filings:
                    details = self.get_company_details(company_number)
                    
                    for filing in filings:
                        self.results.append({
                            "location": property_name,
                            "postcode": postcode,
                            "company_number": company_number,
                            "company_name": company_name,
                            "status": details.get("status"),
                            "type": details.get("type"),
                            "website": details.get("website", ""),
                            "filing_date": filing.get("date"),
                            "days_since_filing": filing.get("days_ago"),
                            "sic_codes": ", ".join(details.get("sic_codes", [])),
                            "discovered_at": datetime.now().isoformat()
                        })
        
        self.results.sort(key=lambda x: x.get("days_since_filing", 999))
        self.scan_status = "complete"
        
        if progress_callback:
            progress_callback({
                "status": "complete",
                "results_found": len(self.results),
                "total": total_postcodes
            })

tracker = None

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/start-scan', methods=['POST'])
def start_scan():
    global tracker
    data = request.json
    # Use hardcoded API key or from request
    api_key = data.get('api_key') or "70fbf4df-44bc-4598-9673-577e38ded898"

    if not api_key:
        return jsonify({"error": "API key required"}), 400

    tracker = CompaniesHouseTracker(api_key)
    
    def progress_callback(status):
        pass
    
    thread = threading.Thread(target=tracker.run_scan, args=(progress_callback,))
    thread.daemon = True
    thread.start()
    
    return jsonify({"status": "scanning"})

@app.route('/api/results')
def get_results():
    global tracker

    if not tracker:
        return jsonify({"error": "No scan in progress"}), 400

    return jsonify({
        "status": tracker.scan_status,
        "results": tracker.results,
        "count": len(tracker.results),
        **tracker.progress
    })

@app.route('/api/download-csv')
def download_csv():
    global tracker
    
    if not tracker or not tracker.results:
        return jsonify({"error": "No results to download"}), 400
    
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=tracker.results[0].keys())
    writer.writeheader()
    writer.writerows(tracker.results)
    
    csv_bytes = BytesIO()
    csv_bytes.write(output.getvalue().encode('utf-8'))
    csv_bytes.seek(0)
    
    return send_file(
        csv_bytes,
        mimetype='text/csv',
        as_attachment=True,
        download_name=f'company_moves_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
    )

if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=False, host='0.0.0.0', port=port)
