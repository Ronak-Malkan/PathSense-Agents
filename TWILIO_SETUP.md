# Twilio SMS Setup Guide

## Quick Setup (5 minutes)

Follow these steps to enable real SMS alerts in PathSense.

---

## Step 1: Get Twilio Credentials

### 1.1 Sign Up for Twilio

If you haven't already, sign up at: https://www.twilio.com/try-twilio

- ✅ Free trial includes $15.00 credit
- ✅ Enough for ~500 SMS messages
- ✅ No credit card required for trial

### 1.2 Get Your Account SID and Auth Token

1. Go to **Twilio Console**: https://console.twilio.com
2. You'll see your **Account SID** and **Auth Token** on the dashboard
3. Click the **eye icon** to reveal your Auth Token

**Example:**
```
Account SID: ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
Auth Token: your_auth_token_here
```

**⚠️ Keep these secret!** Never commit them to git or share publicly.

### 1.3 Get a Twilio Phone Number

1. In Twilio Console, go to **Phone Numbers** → **Manage** → **Buy a number**
2. Choose your country (e.g., United States)
3. Search for an available number
4. Click **Buy** (it's free with trial credit!)

**Example:**
```
Your Twilio Number: +1 555 123 4567
```

---

## Step 2: Configure PathSense

### 2.1 Create .env File

In your PathSense-Agents directory, create a file named `.env`:

```bash
cd /Users/ronakmalkan/code/PathSense-Agents
touch .env
```

### 2.2 Add Your Credentials

Open `.env` and add your Twilio credentials:

```env
# Twilio Configuration
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=your_auth_token_here
TWILIO_PHONE_NUMBER=+15551234567
```

**Replace with your actual values:**
- `TWILIO_ACCOUNT_SID` - Your Account SID from Twilio Console
- `TWILIO_AUTH_TOKEN` - Your Auth Token from Twilio Console
- `TWILIO_PHONE_NUMBER` - Your Twilio phone number (include country code with +)

**Example:**
```env
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=your_auth_token_here
TWILIO_PHONE_NUMBER=+1XXXXXXXXXX
```

### 2.3 Verify .env File

Make sure:
- ✅ File is named exactly `.env` (with the dot)
- ✅ Located in `/Users/ronakmalkan/code/PathSense-Agents/`
- ✅ Contains all three variables
- ✅ Phone number starts with `+` and country code

---

## Step 3: Verify Emergency Contact Phone

### 3.1 Check Trial Account Restrictions

⚠️ **Twilio trial accounts can only send SMS to verified phone numbers.**

1. Go to **Twilio Console** → **Phone Numbers** → **Manage** → **Verified Caller IDs**
2. Click **Add a new number**
3. Enter the emergency contact phone number (e.g., `+14085693812`)
4. Twilio will call/text that number with a verification code
5. Enter the code to verify

**Once verified, you can send SMS to that number!**

### 3.2 Upgrade to Remove Restrictions (Optional)

To send SMS to any number without verification:
1. Go to **Billing** in Twilio Console
2. Add credit card and upgrade account
3. Now you can send to any phone number

---

## Step 4: Test SMS Integration

### 4.1 Restart the Server

Stop your PathSense server (Ctrl+C) and restart it:

```bash
python app.py
```

You should see the server start normally. The `.env` file is loaded automatically.

### 4.2 Trigger a Test Alert

**Option A: Use Your Android App**

Navigate in a way that triggers a stuck scenario:
- Send only `STOP` or `CAUTION` events (no `CLEAR`) for 100+ seconds

**Option B: Send Test Logs via API**

```bash
# Send 40 STOP events (will trigger stuck alert)
curl -X POST http://localhost:5000/api/ingest/batch \
  -H "Content-Type: application/json" \
  -d '{
    "logs": [
      {"client_id": "test123", "session_id": "session1", "t": '$(date +%s)', "events": ["STOP"], "classes": ["car"], "confidence": 0.8},
      {"client_id": "test123", "session_id": "session1", "t": '$(($(date +%s) + 3))', "events": ["STOP"], "classes": ["car"], "confidence": 0.8},
      ...
    ]
  }'
```

### 4.3 Check Server Console

You should see:

```
[WATCHDOG] 🚨 Stuck alert sent for test123: 105s with no CLEAR events
[ALERT] ✅ SMS sent to +14085693812
[ALERT] Message SID: SMxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
[ALERT] Status: queued
```

### 4.4 Check Your Phone

Within a few seconds, you should receive an SMS like:

```
🚨 PathSense ALERT

User unable to proceed for 105 seconds. Repeated obstacles with no clear path.

Time: 01:30 PM

Please check on the user immediately.
```

---

## Troubleshooting

### Issue: "Twilio credentials not configured"

**Cause:** `.env` file not found or variables not set correctly

**Fix:**
1. Verify `.env` file exists in the correct location
2. Check variable names are exactly: `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_PHONE_NUMBER`
3. No quotes around values in `.env`
4. Restart the server after creating/editing `.env`

### Issue: "The number +1XXXXXXXXXX is unverified"

**Cause:** Trial account can only send to verified numbers

**Fix:**
1. Go to Twilio Console → Verified Caller IDs
2. Verify the emergency contact phone number
3. Or upgrade your Twilio account to send to any number

### Issue: "Unable to create record: Authenticate"

**Cause:** Invalid Account SID or Auth Token

**Fix:**
1. Double-check credentials in Twilio Console
2. Make sure you copied them correctly (no extra spaces)
3. Regenerate Auth Token if needed (in Twilio Console)

### Issue: SMS not received

**Possible causes:**
1. **Check Twilio Console Logs**:
   - Go to **Monitor** → **Logs** → **Messaging**
   - See detailed delivery status

2. **Phone number format**:
   - Must include `+` and country code
   - Example: `+14085693812` (not `4085693812`)

3. **Carrier blocking**:
   - Some carriers block SMS from trial accounts
   - Try a different phone number or upgrade Twilio account

4. **Trial credit exhausted**:
   - Check **Billing** in Twilio Console
   - Add more credit if needed

---

## SMS Message Format

PathSense sends different messages for different alert types:

### Stuck Alert
```
🚨 PathSense ALERT

User unable to proceed for 105 seconds. Repeated obstacles with no clear path.

Time: 02:15 PM

Please check on the user immediately.
```

### Danger Surge Alert
```
⚠️ PathSense ALERT

User encountered 12 STOP events in the last minute. Possible dangerous/chaotic area.

Time: 02:20 PM

Please check on the user immediately.
```

### Inactivity Alert
```
⚠️ PathSense ALERT

No navigation activity for 10 minutes. App may have crashed or user may need assistance.

Time: 02:30 PM

Please check on the user immediately.
```

### Maneuvering Alert
```
⚠️ PathSense ALERT

User changed direction 9 times in ~45 seconds. May be disoriented or lost.

Time: 02:35 PM

Please check on the user immediately.
```

---

## Cost Information

### Trial Account
- **Free credit:** $15.00
- **SMS cost:** ~$0.0075 per message (US)
- **Total messages:** ~2000 SMS with trial credit

### Paid Account
- **Monthly fee:** $0 (pay as you go)
- **SMS cost:** $0.0079 per message (US)
- **No minimum spend**

**For this project:** Trial credit is more than enough for testing and demonstration!

---

## Security Best Practices

### ✅ DO:
- Keep `.env` file in `.gitignore` (already configured)
- Use environment variables for sensitive data
- Regenerate Auth Token if exposed
- Monitor Twilio Console for unusual activity

### ❌ DON'T:
- Commit `.env` to git
- Share credentials publicly
- Hardcode credentials in source code
- Use production credentials in development

---

## Next Steps

Once SMS is working:

1. ✅ Test all 4 emergency alert patterns
2. ✅ Verify alerts are saved to database
3. ✅ Test with real navigation scenarios
4. ✅ Deploy to production (Agentverse)

---

## Reference Links

- **Twilio Console:** https://console.twilio.com
- **Twilio SMS Documentation:** https://www.twilio.com/docs/sms
- **Python Client Library:** https://www.twilio.com/docs/libraries/python
- **Pricing:** https://www.twilio.com/pricing/messaging

---

**Your SMS integration is now complete!** 🎉

Every emergency alert will now send an actual SMS to the registered emergency contact.
