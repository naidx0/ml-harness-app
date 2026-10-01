from app import db
import csv
import io

def run_to_csv(run_id: int) -> str:
    metrics = db.metrics_for(run_id)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["step", "name", "value"])
    for m in metrics:
        writer.writerow([m["step"], m["name"], m["value"]])
    return buf.getvalue()
