# -*- coding: utf-8 -*-
"""Synthetic prompts. Everything is invented: no real customers, IDs or numbers.

gold = what the router never sees: true task, true language bucket, a
human-assigned difficulty (1-5), expected output length, and the checks the
offline eval uses to score answers in live mode.
"""

VOICE = {"channel": "voice", "latency_budget_ms": 1500}
INTENTS = "refund, cancel_order, delivery_status, payment_failed, other"


def P(id, content, task, lang, d, out, checks, out_script=None, meta=None, tools=None, wants_json=False):
    return {"id": id, "messages": [{"role": "user", "content": content}], "meta": meta or {},
            "tools": tools or [],
            "gold": {"task": task, "lang_bucket": lang, "difficulty": d, "out_tokens": out,
                     "out_script": out_script, "checks": checks, "wants_json": wants_json}}


def T(name, desc, **params):
    return {"name": name, "description": desc,
            "parameters": {"type": "object", "properties": {k: {"type": v} for k, v in params.items()}}}


label = lambda v: [{"type": "label", "value": v}]
keys = lambda *k: [{"type": "json_keys", "keys": list(k)}]
kw = lambda *w: [{"type": "keywords", "words": list(w)}]
script = lambda s: [{"type": "script", "script": s}]
tool = lambda n: [{"type": "tool_call", "name": n}]

CALL_EN = """Agent: Thank you for calling, this is Meera. Customer: Hi, my broadband has been down since Tuesday and I work from home. Agent: I'm sorry. I see an outage in your area; technicians are on it. Customer: I've already lost two days of work. Agent: I'll add a 7-day service credit and escalate the ticket to priority. Expected restoration is tomorrow 6 pm. Customer: Fine, but call me if it slips. Agent: Noted, we'll call you by 5 pm tomorrow."""

CALL_HINGLISH = """Agent: Namaste, main Priya bol rahi hoon XYZ Finance se. Customer: haan, mera EMI ka auto-debit is mahine do baar ho gaya hai, 8,200 do baar kat gaye. Agent: Sorry sir, main check karti hoon... haan, duplicate debit dikh raha hai. Refund 5 working days mein aa jayega. Customer: 5 din? mujhe rent dena hai. Agent: main ise priority pe daal deti hoon, 48 ghante mein try karenge. Customer: theek hai, SMS bhej dena. Agent: ji, ticket number bhi SMS kar dungi."""

CALL_HINGLISH_2 = """Agent: Hello, main Arjun, SafeLife Insurance se. Customer: haan bhai, mera claim 3 hafte se pending hai, hospital ka bill 64,000 ka tha. Agent: sir, aapke documents mein discharge summary missing hai. Customer: maine email pe bheja tha 12 tareekh ko. Agent: mujhe mil gaya, lekin doctor ka sign nahi hai. Customer: toh pehle kyun nahi bataya? Agent: sorry sir, main ab ise re-open kar raha hoon, signed copy upload kar dijiye, 7 din mein settle hoga. Aapko policy renewal ke saath naya top-up plan bhi chahiye? Customer: abhi nahi, pehle claim do."""

HELDOUT = [
    # ---------------- English: classification
    P("H01", "Classify the customer's intent into one of: %s. Reply with only the label.\n\nCustomer: I paid twice for the same order yesterday, when will I get one of them back?" % INTENTS,
      "classify", "en", 1, 3, label("refund")),
    P("H02", "Classify the customer's intent into one of: %s. Reply with only the label.\n\nCustomer: Where is my parcel? It has said out for delivery since morning." % INTENTS,
      "classify", "en", 1, 3, label("delivery_status")),
    P("H03", "Label the sentiment of this review as positive, negative or mixed. Answer with one word.\nReview: The agent was polite but it took three calls and 40 minutes to fix a simple address change.",
      "classify", "en", 2, 2, label("mixed")),
    P("H04", "Classify into exactly one of: fraud_report, card_block, limit_increase, other. Reply with only the label.\nCustomer: Someone just used my card in Dubai and I am in Pune. Stop it and tell me if I get the money back.",
      "classify", "en", 2, 3, label("fraud_report")),
    # ---------------- English: extraction
    P("H05", "Extract the following fields as JSON with keys invoice_number, date, gstin, total_amount, vendor.\n\nTAX INVOICE No. INV-2291 dated 14/03/2026 from Shree Ganesh Traders, GSTIN 27ABCDE1234F1Z5. Items: 40 cartons @ 350. Total payable Rs 16,520 incl. GST.",
      "extract", "en", 2, 80, keys("invoice_number", "date", "gstin", "total_amount", "vendor"), wants_json=True),
    P("H06", "Extract a JSON object with keys claimant, policy_number and incidents (a list; each item has date, description, amount). Do not invent values; use null if missing.\n\nNote: Claimant Anita Rao (policy HX-77120) reports: water damage on 2 Feb costing 18,000; stolen laptop on 9 Feb, about 62,000; and a cracked windshield on 11 Feb, amount not yet assessed.",
      "extract", "en", 3, 160, keys("claimant", "policy_number", "incidents"), wants_json=True),
    P("H07", "From this email, extract JSON with keys meeting_date, time, location, attendees.\n\nHi all, let's meet on Thursday 9 April at 3:30 pm in the Koramangala office, 4th floor. Rahul, Sana and Deepak please join; Kiran is optional.",
      "extract", "en", 2, 60, keys("meeting_date", "time", "location", "attendees"), wants_json=True),
    # ---------------- English: summarisation
    P("H08", "Summarise this support call in 3 bullet points.\n\n" + CALL_EN,
      "summarize", "en", 2, 80, kw("outage", "credit", "tomorrow")),
    P("H09", "Summarise this call for a compliance auditor. You must:\n- list every commitment the agent made\n- flag any mis-selling risk\n- state whether a callback time was agreed\n- keep it under 120 words\n\n" + CALL_EN,
      "summarize", "en", 3, 160, kw("credit", "escalat", "5 ?pm|callback", "6 ?pm|restor")),
    P("H10", "Summarise the key obligations for the customer in this policy excerpt in 4 bullets.\n\nThe insured must notify the insurer within 7 days of any loss. Claims above Rs 50,000 require a surveyor inspection before repairs begin. The insured must keep all damaged items for 30 days. Premiums are payable annually; a 15-day grace period applies, during which cover remains active but claims are paid only after the premium is received. Any misstatement of material facts voids the policy.",
      "summarize", "en", 3, 120, kw("7 days", "surveyor", "30 days", "grace")),
    # ---------------- English: code
    P("H11", "Write a Python function validate_gstin(s) that checks an Indian GSTIN: 15 characters, first 2 digits a state code 01-38, next 10 a valid PAN pattern, 13th an entity number, 14th 'Z', and the 15th a checksum computed with the official mod-36 algorithm. Include the checksum implementation and 3 test cases.",
      "code", "en", 4, 350, kw("def validate_gstin", "36", "assert|test")),
    P("H12", "Given tables calls(id, agent_id, started_at, duration_s, language) and agents(id, name, team), write a SQL query returning the top 3 agents by average handle time for each language over the last 30 days.",
      "code", "en", 3, 150, kw("select", "avg", "partition by|rank|row_number", "30")),
    P("H13", "Fix the bug:\n```python\ndef avg_handle_time(calls):\n    total = 0\n    for c in calls:\n        total += c['duration']\n    return total / len(calls)\n```\nIt crashes when there are no calls on a holiday.",
      "code", "en", 2, 100, kw("len\\(calls\\)|not calls|if calls", "return")),
    # ---------------- English: reasoning
    P("H14", "We process 12M tokens a month, 30% of them Hindi. Plan A costs $0.80 per 1M tokens flat. Plan B costs $0.50 per 1M for English and $1.40 per 1M for Hindi, but Hindi uses 1.6x fewer tokens on Plan B's tokenizer. Which plan is cheaper per month? Calculate step by step.",
      "reasoning", "en", 4, 300, kw("plan a", "plan b", "9\\.6|9\\.60", "cheaper")),
    P("H15", "Clause 4.2: Either party may terminate with 60 days' notice. Clause 7.1: Minimum commitment is 12 months from go-live. Clause 7.3: Early termination fee equals 50% of the remaining minimum commitment. Go-live was 1 March 2026 and the monthly fee is Rs 4 lakh. If we give notice on 1 August 2026, what is the earliest termination date and the fee? Explain your reasoning.",
      "reasoning", "en", 4, 300, kw("30 sep|september 30|1 oct|october", "lakh|10,00,000|1,000,000|10 lakh")),
    P("H16", "Schedule 5 agents (A-E) across 3 shifts (morning, evening, night) for one day. Constraints: every shift needs at least one Hindi speaker (A, C, E); B and D cannot work the same shift; E cannot work nights; night needs 2 people; each agent works exactly one shift. Give a valid schedule and prove it satisfies all constraints.",
      "reasoning", "en", 5, 350, kw("night", "morning", "evening")),
    # ---------------- English: tools
    P("H17", "Customer says order 88213 arrived damaged and wants a refund. Handle it.",
      "tool_use", "en", 3, 60, tool("create_refund"),
      tools=[T("get_order_status", "Get order status", order_id="string"),
             T("create_refund", "Create a refund", order_id="string", reason="string")]),
    P("H18", "Book the earliest available slot next week for a home loan consultation at the Andheri branch for customer C-1182, then send them an SMS confirmation. If no slot exists, add them to the waitlist.",
      "tool_use", "en", 4, 120, tool("book_slot"),
      tools=[T("find_slots", "Find slots", branch="string", week="string"),
             T("book_slot", "Book slot", slot_id="string", customer_id="string"),
             T("send_sms", "Send SMS", customer_id="string", text="string"),
             T("add_waitlist", "Add to waitlist", customer_id="string", branch="string")]),
    # ---------------- Indic: classification
    P("H19", "ग्राहक का इरादा बताइए: %s. सिर्फ़ लेबल लिखें।\nग्राहक: मेरा ऑर्डर अभी तक नहीं आया, कब तक आएगा?" % INTENTS,
      "classify", "indic", 1, 3, label("delivery_status")),
    P("H20", "इस समीक्षा की भावना बताइए (positive / negative / mixed), एक शब्द में।\nसमीक्षा: सेवा अच्छी थी लेकिन डिलीवरी बहुत देर से हुई और पैकेट फटा हुआ था।",
      "classify", "indic", 2, 2, label("mixed")),
    P("H21", "Classify intent (%s). Only label.\nCustomer: bhai mera payment fail ho gaya par paise account se kat gaye, ab kya karu?" % INTENTS,
      "classify", "mixed", 2, 3, label("payment_failed")),
    P("H22", "ग्राहकाचा हेतू ओळखा: %s. फक्त लेबल लिहा.\nग्राहक: मला माझी ऑर्डर रद्द करायची आहे, चुकीचा आकार निवडला." % INTENTS,
      "classify", "indic", 1, 3, label("cancel_order")),
    # ---------------- Hinglish: summarisation
    P("H23", "Summarise this call in 3 bullet points in English.\n\n" + CALL_HINGLISH,
      "summarize", "mixed", 2, 80, kw("emi|debit", "twice|double|duplicate", "refund", "48")),
    P("H24", "Is call ka summary Hindi mein do lines mein likho.\n\n" + CALL_HINGLISH,
      "summarize", "mixed", 3, 80, script("deva"), out_script="deva"),
    P("H25", "Summarise this call. You must: list the customer's complaint, every commitment the agent made, flag any cross-selling, and state the next step. Answer in English.\n\n" + CALL_HINGLISH_2,
      "summarize", "mixed", 4, 160, kw("claim", "discharge|signature|sign", "7 days|seven", "top-up|cross")),
    # ---------------- translation
    P("H26", "Translate into Hindi: Your KYC documents have been verified. Your account will be activated within 24 hours.",
      "translate", "indic", 2, 40, script("deva") + kw("24"), out_script="deva"),
    P("H27", "Translate into Tamil: Please keep your policy number ready before calling the helpline.",
      "translate", "indic", 2, 40, script("taml"), out_script="taml"),
    P("H28", "Translate to English: कृपया अपना मोबाइल नंबर अपडेट करने के लिए नज़दीकी शाखा में जाएँ। आधार कार्ड साथ लाना अनिवार्य है।",
      "translate", "indic", 2, 40, kw("mobile", "branch", "aadhaar|aadhar")),
    # ---------------- Indic: QA / summarisation
    P("H29", "கீழே உள்ள பத்தியைப் படித்து தமிழில் பதிலளிக்கவும்.\nபத்தி: பயிர் காப்பீட்டுத் திட்டத்தில் சேர விவசாயிகள் விதைப்பு முடிந்த 10 நாட்களுக்குள் விண்ணப்பிக்க வேண்டும். பிரீமியம் காரீஃப் பயிர்களுக்கு 2% ஆகும்.\nகேள்வி: விண்ணப்பிக்க கடைசி காலம் என்ன, பிரீமியம் எவ்வளவு?",
      "chat", "indic", 3, 60, script("taml") + kw("10", "2"), out_script="taml"),
    P("H30", "নিচের অনুচ্ছেদটি বাংলায় এক লাইনে সংক্ষেপ করুন।\nঅনুচ্ছেদ: ব্যাংক ১ এপ্রিল থেকে সব সঞ্চয় অ্যাকাউন্টে ন্যূনতম ব্যালেন্স ৫,০০০ টাকা করেছে। এর কম হলে মাসে ১০০ টাকা জরিমানা হবে, তবে প্রবীণ নাগরিকদের ছাড় দেওয়া হবে।",
      "summarize", "indic", 2, 40, script("beng"), out_script="beng"),
    # ---------------- voice turns (latency budget)
    P("H31", "आप एक बैंक के वॉइस असिस्टेंट हैं। खाते का बैलेंस ₹12,450 है। ग्राहक: मेरा बैलेंस कितना है? छोटा जवाब दें।",
      "chat", "indic", 1, 25, script("deva") + kw("12,?450|१२,?४५०"), out_script="deva", meta=VOICE),
    P("H32", "You are a voice agent for a telecom. Reply in Hinglish, max 2 sentences.\nCustomer: mera data pack khatam ho gaya, naya recharge kaise karu?",
      "chat", "mixed", 1, 40, kw("recharge", "app|\\*|ussd|website"), meta=VOICE),
    P("H33", "You are a voice agent for a courier. Policy: deliveries can be rescheduled up to 2 times, weekends allowed. Reply in one sentence.\nCustomer: can I move my delivery to Saturday?",
      "chat", "en", 1, 30, kw("yes|sure|can", "saturday"), meta=VOICE),
    # ---------------- Indic: extraction
    P("H34", "नीचे दिए गए आवेदन से JSON निकालें, keys: name, loan_amount, tenure_months, purpose.\nआवेदन: मेरा नाम सुरेश यादव है। मुझे अपनी दुकान के विस्तार के लिए ₹3,50,000 का ऋण 24 महीनों के लिए चाहिए।",
      "extract", "indic", 2, 60, keys("name", "loan_amount", "tenure_months", "purpose"), wants_json=True),
    P("H35", "नीचे की शिकायत से JSON निकालें: keys complainant, items (list, हर item में item, value), total_value. कोई मान न हो तो null लिखें।\nशिकायत: मैं कविता शर्मा, 5 मार्च को मेरे घर से एक सोने की चेन (लगभग ₹85,000), एक मोबाइल (₹22,000) और कुछ नकद चोरी हो गए।",
      "extract", "indic", 3, 120, keys("complainant", "items", "total_value"), wants_json=True),
    # ---------------- Kannada / Telugu
    P("H36", "Summarise in English in 2 lines:\nಬೆಂಗಳೂರು ಮಹಾನಗರ ಪಾಲಿಕೆಯು ಆಸ್ತಿ ತೆರಿಗೆಯನ್ನು ಏಪ್ರಿಲ್ 30ರೊಳಗೆ ಪಾವತಿಸಿದರೆ 5% ರಿಯಾಯಿತಿ ನೀಡುತ್ತದೆ. ತಡವಾಗಿ ಪಾವತಿಸಿದರೆ ತಿಂಗಳಿಗೆ 2% ದಂಡ ವಿಧಿಸಲಾಗುತ್ತದೆ.",
      "summarize", "indic", 3, 50, kw("property tax", "5 ?%", "april 30|30 april", "2 ?%")),
    P("H37", "ఈ వార్తను తెలుగులో ఒక వాక్యంలో సంక్షిప్తం చేయండి: రాష్ట్ర ప్రభుత్వం రైతులకు ఎకరాకు 10,000 రూపాయల పెట్టుబడి సాయం ప్రకటించింది, ఇది రెండు విడతలుగా చెల్లించబడుతుంది.",
      "summarize", "indic", 2, 40, script("telu"), out_script="telu"),
    # ---------------- Indic reasoning / tools
    P("H38", "Mera loan 5 lakh ka hai, 10% annual interest, 3 saal ke liye. Monthly EMI kitni banegi? Step by step calculate karke batao.",
      "reasoning", "mixed", 4, 250, kw("16,?13[34]|16,?1[0-9]{2}")),
    P("H39", "mera card kho gaya hai, jaldi block karo, card last 4 digits 4421. Aur balance bhi batao.",
      "tool_use", "mixed", 3, 60, tool("block_card"),
      tools=[T("block_card", "Block a card", last4="string"),
             T("check_balance", "Get account balance", account_id="string")]),
    P("H40", "प्रधानमंत्री आवास योजना के लिए पात्रता: परिवार की वार्षिक आय ₹3 लाख से कम हो, परिवार के किसी सदस्य के नाम पक्का मकान न हो, और आवेदक की आयु 18 वर्ष से अधिक हो। रमेश (उम्र 34) की आय ₹2.8 लाख है, लेकिन उसकी पत्नी के नाम गाँव में पक्का मकान है। क्या रमेश पात्र है? कारण सहित हिंदी में बताइए।",
      "reasoning", "indic", 4, 150, script("deva") + kw("नहीं|अपात्र"), out_script="deva"),
]

CALIBRATION = [
    P("C01", "Classify the customer's intent into one of: %s. Reply with only the label.\nCustomer: I want to cancel the shoes I ordered an hour ago." % INTENTS,
      "classify", "en", 1, 3, label("cancel_order")),
    P("C02", "Label the sentiment as positive, negative or mixed. One word.\nReview: Delivery was on time and the product works perfectly.",
      "classify", "en", 1, 2, label("positive")),
    P("C03", "Extract JSON with keys name, phone, city from: 'Hi, I'm Farhan Qureshi from Lucknow, reach me on 98XXXXXX10.'",
      "extract", "en", 2, 40, keys("name", "phone", "city"), wants_json=True),
    P("C04", "Extract a JSON object with keys order_id and items (a list with sku, qty, price) from: Order #5521: 2x SKU-A11 at 499, 1x SKU-B07 at 1299, 3x SKU-C02 at 99.",
      "extract", "en", 3, 120, keys("order_id", "items"), wants_json=True),
    P("C05", "Summarise in 2 bullets: The customer called about a delayed refund of Rs 2,300 for a cancelled flight. The agent confirmed the refund was initiated on 3 May and will reach the card in 7 working days.",
      "summarize", "en", 2, 60, kw("refund", "7")),
    P("C06", "Write a Python function that masks all but the last 4 digits of a 12-digit account number and add a unit test.",
      "code", "en", 2, 120, kw("def", "assert")),
    P("C07", "Write a SQL query that finds customers who called support more than 3 times in any rolling 7-day window. Tables: calls(customer_id, started_at).",
      "code", "en", 4, 200, kw("select", "interval|range|between")),
    P("C08", "A call centre has 40 agents. Each handles 9 calls/hour, 20% of calls need a callback that takes 1.5x the time. How many effective calls per hour does the centre handle? Calculate step by step.",
      "reasoning", "en", 3, 200, kw("300|3\\d\\d")),
    P("C09", "Compare two vendors step by step and recommend one: Vendor X charges 2 lakh setup plus 0.40 per call; Vendor Y charges nothing upfront but 0.65 per call. We expect 90,000 calls a year for 3 years. Justify the trade-off.",
      "reasoning", "en", 4, 250, kw("vendor x|x", "break-?even|8,?00,000|800000")),
    P("C10", "Customer wants to know the status of order 7781.",
      "tool_use", "en", 2, 40, tool("get_order_status"),
      tools=[T("get_order_status", "Get order status", order_id="string")]),
    P("C11", "ग्राहक का इरादा बताइए: %s. सिर्फ़ लेबल लिखें।\nग्राहक: पैसे कट गए लेकिन भुगतान असफल दिखा रहा है।" % INTENTS,
      "classify", "indic", 1, 3, label("payment_failed")),
    P("C12", "Classify intent (%s). Only label.\nCustomer: order kab aayega yaar, 5 din ho gaye" % INTENTS,
      "classify", "mixed", 1, 3, label("delivery_status")),
    P("C13", "Translate into Hindi: Your complaint has been registered. Reference number 44821.",
      "translate", "indic", 1, 30, script("deva"), out_script="deva"),
    P("C14", "Translate into Tamil: The branch will remain closed on Monday due to a public holiday.",
      "translate", "indic", 2, 30, script("taml"), out_script="taml"),
    P("C15", "Translate to English: আপনার ঋণের আবেদন অনুমোদিত হয়েছে। টাকা দুই দিনের মধ্যে আপনার অ্যাকাউন্টে জমা হবে।",
      "translate", "indic", 2, 30, kw("loan", "approved", "two days|2 days")),
    P("C16", "Summarise this call in 2 bullet points in English.\n\nAgent: Hello, Rohit bol raha hoon. Customer: haan, mera SIM block ho gaya hai, OTP nahi aa raha. Agent: sir, aapka SIM 24 ghante mein reactivate ho jayega, aadhar verify karna padega. Customer: theek hai.",
      "summarize", "mixed", 2, 50, kw("sim", "24", "aadhaar|aadhar")),
    P("C17", "Is call ko Hindi mein ek line mein summarise karo.\n\n" + CALL_HINGLISH_2,
      "summarize", "mixed", 3, 50, script("deva"), out_script="deva"),
    P("C18", "नीचे दिए गए संदेश से JSON निकालें, keys: name, city, complaint.\nसंदेश: मैं अनिल वर्मा, भोपाल से, मेरा बिजली बिल दो महीने से गलत आ रहा है।",
      "extract", "indic", 2, 40, keys("name", "city", "complaint"), wants_json=True),
    P("C19", "ಕೆಳಗಿನ ಪ್ರಶ್ನೆಗೆ ಕನ್ನಡದಲ್ಲಿ ಉತ್ತರಿಸಿ: ಪಡಿತರ ಚೀಟಿಗೆ ಅರ್ಜಿ ಸಲ್ಲಿಸಲು ಯಾವ ದಾಖಲೆಗಳು ಬೇಕು? (ಮಾಹಿತಿ: ಆಧಾರ್, ವಿಳಾಸ ಪುರಾವೆ ಮತ್ತು ಆದಾಯ ಪ್ರಮಾಣಪತ್ರ)",
      "chat", "indic", 2, 50, script("knda"), out_script="knda"),
    P("C20", "आप एक बीमा कंपनी के वॉइस असिस्टेंट हैं। पॉलिसी की अगली किस्त 15 जून को है। ग्राहक: मेरी अगली किस्त कब है? छोटा जवाब दें।",
      "chat", "indic", 1, 20, script("deva"), out_script="deva", meta=VOICE),
    P("C21", "You are a voice agent for a bank. Reply in Hinglish, 1 sentence.\nCustomer: mera cheque book kab tak aayega?",
      "chat", "mixed", 1, 30, kw("cheque|chequebook"), meta=VOICE),
    P("C22", "Mujhe 2 lakh ka personal loan 12% pe 2 saal ke liye lena hai aur doosra option 11% pe 3 saal. Kaunsa sasta padega total interest mein? Step by step batao.",
      "reasoning", "mixed", 4, 250, kw("2 saal|2 year|first|pehla")),
    P("C23", "किसान क्रेडिट कार्ड की पात्रता: किसान की उम्र 18-75 वर्ष, खुद की या पट्टे की ज़मीन। सुनीता 62 वर्ष की हैं और पट्टे की ज़मीन पर खेती करती हैं। क्या वे पात्र हैं? कारण सहित हिंदी में बताइए।",
      "reasoning", "indic", 3, 100, script("deva") + kw("हाँ|हां|पात्र"), out_script="deva"),
    P("C24", "mera UPI payment atak gaya hai, transaction ID T88120 check karo aur zarurat ho to dispute raise karo.",
      "tool_use", "mixed", 3, 60, tool("raise_dispute"),
      tools=[T("check_txn", "Check transaction", txn_id="string"),
             T("raise_dispute", "Raise dispute", txn_id="string", reason="string")]),
]
