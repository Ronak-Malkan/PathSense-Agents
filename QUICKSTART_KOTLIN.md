# Quick Start: Integrating PathSense with Your Kotlin App

## 🚀 Fast Track Integration Guide

This guide gets you integrated in 15 minutes.

---

## Step 1: Start the PathSense API (5 minutes)

```bash
# In PathSense-Agents directory

# 1. Install dependencies (one-time)
pip install -r requirements.txt

# 2. Initialize database (one-time)
python database.py

# 3. Start server
python app.py
```

**Output:**
```
============================================================
PathSense Navigation Monitoring API
============================================================
...
Starting server on http://localhost:5000
```

**Note:** If port 5000 is in use, edit `app.py` line 441 to use port 5001

---

## Step 2: Get Your Computer's IP (1 minute)

```bash
# macOS/Linux
ifconfig | grep "inet " | grep -v 127.0.0.1

# Windows
ipconfig
```

Example output: `inet 192.168.1.100`

**Use this IP in your Kotlin app** (not localhost!)

---

## Step 3: Add to Your Kotlin Project (5 minutes)

### Add Dependencies (build.gradle.kts)

```kotlin
dependencies {
    implementation("com.squareup.okhttp3:okhttp:4.12.0")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.7.3")
}
```

### Create PathSenseAPI.kt

```kotlin
package com.yourapp.pathsense

import okhttp3.*
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONArray
import org.json.JSONObject
import java.io.IOException

object PathSenseAPI {
    private const val BASE_URL = "http://192.168.1.100:5000"  // ⚠️ CHANGE TO YOUR IP
    private val client = OkHttpClient()
    private val JSON = "application/json".toMediaType()

    // Call once during app setup
    fun registerUser(
        clientId: String,
        contactId: String,
        contactPhone: String,
        callback: (Boolean, String) -> Unit
    ) {
        val payload = JSONObject().apply {
            put("client_id", clientId)
            put("emergency_contacts", JSONArray().apply {
                put(JSONObject().apply {
                    put("contact_id", contactId)
                    put("phone", contactPhone)
                    put("name", "Emergency Contact")
                    put("relationship", "caretaker")
                })
            })
        }

        val request = Request.Builder()
            .url("$BASE_URL/api/register")
            .post(payload.toString().toRequestBody(JSON))
            .build()

        client.newCall(request).enqueue(object : Callback {
            override fun onFailure(call: Call, e: IOException) {
                callback(false, e.message ?: "Network error")
            }

            override fun onResponse(call: Call, response: Response) {
                val success = response.isSuccessful
                val message = response.body?.string() ?: "Unknown response"
                callback(success, message)
            }
        })
    }

    // Call every 3 seconds during navigation
    fun sendLog(
        clientId: String,
        sessionId: String,
        events: List<String>,  // e.g., ["STOP", "CAUTION"]
        classes: List<String>,  // e.g., ["person", "car"]
        confidence: Float
    ) {
        val payload = JSONObject().apply {
            put("client_id", clientId)
            put("session_id", sessionId)
            put("t", System.currentTimeMillis() / 1000)  // Unix seconds
            put("events", JSONArray(events))
            put("classes", JSONArray(classes))
            put("confidence", confidence)
        }

        val request = Request.Builder()
            .url("$BASE_URL/api/ingest")
            .post(payload.toString().toRequestBody(JSON))
            .build()

        client.newCall(request).execute()  // Fire and forget
    }
}
```

---

## Step 4: Integrate with Your Navigation Activity (5 minutes)

### In Your NavigationActivity or ViewModel:

```kotlin
import android.content.Context
import android.provider.Settings
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import java.security.MessageDigest
import java.util.UUID

class NavigationViewModel(private val context: Context) : ViewModel() {

    private var isNavigating = false
    private lateinit var clientId: String
    private lateinit var sessionId: String

    // Initialize user (call once when app first runs)
    fun initializeUser(contactPhone: String) {
        clientId = generateClientId()
        val contactId = generateContactId()

        PathSenseAPI.registerUser(clientId, contactId, contactPhone) { success, message ->
            if (success) {
                // Save clientId to SharedPreferences for future use
                saveClientId(clientId)
                android.util.Log.d("PathSense", "User registered successfully")
            } else {
                android.util.Log.e("PathSense", "Registration failed: $message")
            }
        }
    }

    // Start navigation session
    fun startNavigation() {
        sessionId = UUID.randomUUID().toString()
        isNavigating = true

        // Load clientId from SharedPreferences
        clientId = loadClientId()

        // Start periodic logging
        viewModelScope.launch {
            while (isNavigating) {
                sendCurrentNavigationState()
                delay(3000)  // 3 seconds
            }
        }
    }

    // Stop navigation session
    fun stopNavigation() {
        isNavigating = false
    }

    // Called from your YOLO detection code
    private fun sendCurrentNavigationState() {
        // Get current navigation state from YOLO detection
        val events = getCurrentEvents()  // Returns ["STOP"], ["CLEAR"], etc.
        val classes = getDetectedClasses()  // Returns ["person", "car"], etc.
        val confidence = getModelConfidence()  // Returns 0.0-1.0

        PathSenseAPI.sendLog(
            clientId = clientId,
            sessionId = sessionId,
            events = events,
            classes = classes,
            confidence = confidence
        )
    }

    // Example: Convert your ActionToken to event strings
    private fun getCurrentEvents(): List<String> {
        // YOUR EXISTING CODE HERE
        // Example:
        val currentAction = determineActionFromYOLO()  // Your existing method
        return listOf(currentAction.name)  // Returns "CLEAR", "STOP", etc.
    }

    private fun getDetectedClasses(): List<String> {
        // YOUR EXISTING CODE HERE
        // Example: return list of detected YOLO classes
        return detectedObjects.map { it.className }
    }

    private fun getModelConfidence(): Float {
        // YOUR EXISTING CODE HERE
        // Example: return average confidence of detections
        return detectedObjects.map { it.confidence }.average().toFloat()
    }

    // Helper functions
    private fun generateClientId(): String {
        val deviceId = Settings.Secure.getString(
            context.contentResolver,
            Settings.Secure.ANDROID_ID
        )
        val uuid = UUID.randomUUID().toString()
        return sha256("$deviceId-$uuid").take(16)
    }

    private fun generateContactId(): String {
        return UUID.randomUUID().toString().replace("-", "").take(16)
    }

    private fun sha256(input: String): String {
        val bytes = MessageDigest.getInstance("SHA-256").digest(input.toByteArray())
        return bytes.joinToString("") { "%02x".format(it) }
    }

    private fun saveClientId(id: String) {
        context.getSharedPreferences("pathsense", Context.MODE_PRIVATE)
            .edit()
            .putString("client_id", id)
            .apply()
    }

    private fun loadClientId(): String {
        return context.getSharedPreferences("pathsense", Context.MODE_PRIVATE)
            .getString("client_id", "") ?: ""
    }
}
```

---

## Step 5: Test It! (5 minutes)

### 1. Start PathSense API
```bash
python app.py
```

### 2. Run Your App on Android Device

### 3. Watch the Server Console

You should see:
```
[REGISTER] SMS would be sent to +1234567890: Your access code is abc123...
INFO: 127.0.0.1 - - [date] "POST /api/ingest HTTP/1.1" 200 -
INFO: 127.0.0.1 - - [date] "POST /api/ingest HTTP/1.1" 200 -
```

### 4. Trigger an Emergency (for testing)

Navigate in a way that sends only STOP/CAUTION events (no CLEAR) for 100+ seconds.

You should see:
```
[WATCHDOG] 🚨 Stuck alert sent for your_client_id: 105s with no CLEAR events
```

---

## Verification Checklist

- [ ] Server starts without errors
- [ ] App can register user (check server console)
- [ ] App sends logs every 3 seconds (check server console)
- [ ] Logs are saved to database (check with SQLite browser)
- [ ] Emergency alert triggers when simulating stuck scenario
- [ ] Alert appears in database (GET /api/alerts/<client_id>)

---

## Common Issues

### "Connection refused" from Android

**Cause:** Using localhost instead of actual IP

**Fix:**
1. Get your computer's IP: `ifconfig` (macOS/Linux) or `ipconfig` (Windows)
2. Update `BASE_URL` in `PathSenseAPI.kt`
3. Ensure phone and computer on same WiFi network

### "Network Security Policy" error

**Fix:** Add to `AndroidManifest.xml`:
```xml
<application
    android:networkSecurityConfig="@xml/network_security_config"
    ...>
```

Create `res/xml/network_security_config.xml`:
```xml
<?xml version="1.0" encoding="utf-8"?>
<network-security-config>
    <domain-config cleartextTrafficPermitted="true">
        <domain includeSubdomains="true">192.168.1.100</domain>
    </domain-config>
</network-security-config>
```

### No alerts triggering

**Cause:** Not enough logs or pattern not met

**Check:**
1. Verify logs are being sent (check server console)
2. Check watchdog status: `GET http://192.168.1.100:5000/api/watchdog/status/<your_client_id>`
3. Verify pattern conditions:
   - Stuck: 100s with NO "CLEAR" events (only "STOP"/"CAUTION")
   - Danger: 10 "STOP" events within 60 seconds

---

## Next Steps

✅ **Local Testing Complete?**

Move to production:
1. Test with real navigation scenarios
2. Add Twilio integration for actual SMS alerts (edit `tools.py`)
3. Deploy to cloud (Agentverse) for always-on monitoring
4. Add caretaker query interface with ASI:One

---

## Need Help?

1. **Check server logs:** Look at terminal running `python app.py`
2. **Check database:** Open `navigation_logs.db` with SQLite browser
3. **Test API manually:** Use `test_api_simple.py` or curl commands
4. **Review full docs:** See `TESTING_GUIDE.md` for detailed examples

---

**You're all set!** 🎉

Start navigating and PathSense will monitor for emergencies in real-time.
