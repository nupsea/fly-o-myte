
from fly_o_myte.notifier import send_book_now_alert
from fly_o_myte.db.sqlite import Trip, Recommendation
from fly_o_myte.config import get_settings
import logging

# Setup logging to see what's happening
logging.basicConfig(level=logging.INFO)

def test_email():
    settings = get_settings()
    
    print(f"Testing SMTP with Host: {settings.smtp_host}, Port: {settings.smtp_port}, User: {settings.smtp_user}")
    
    # Create a mock trip
    mock_trip = Trip(
        id=999,
        label="Test Trip (SMTP Check)",
        origin="BNE",
        destination="SYD",
        depart_date="2026-12-25",
        return_date="2027-01-05",
        alert_email=settings.default_alert_email
    )
    
    # Create a mock recommendation
    mock_rec = Recommendation(
        decision="book_now",
        confidence=0.95,
        true_family_cost=1250.0,
        regret_risk="low",
        rationale="This is a test email to verify your SMTP configuration via Brevo.",
        generated_at="2026-03-08T10:00:00"
    )
    
    try:
        print("Sending test email...")
        success = send_book_now_alert(mock_trip, mock_rec, settings=settings)
        
        if success:
            print("✅ Success! Check your inbox.")
        else:
            print("❌ Failed. The send_book_now_alert function returned False.")
            print("Check if SMTP_USER and SMTP_PASS are correct.")
            print("For Brevo, SMTP_USER is usually your Brevo account email.")
            print("And SMTP_PASS is your SMTP API Key (Master or specific).")
    except Exception as e:
        print(f"❌ Exception occurred: {e}")

if __name__ == "__main__":
    test_email()
