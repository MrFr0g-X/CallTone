// AUTO-GENERATED from a real processed call (37a3dcdc, MetroBoost billing dispute).
// Audio (public/sample-call.mp3), transcript, and scores all belong to THIS one real call,
// so the sample is fully coherent. No api/auth/token — pure static data for the public /sample page.

export type SampleTurn = {
  role: string; start: number; end: number;
  emotion: string | null; signals: string[]; text: string;
};

export const SAMPLE_CALL = {
  filename: "metroboost_billing_call.wav",
  agentName: "Chalene (agent) · Customer: Linda",
  callTime: "2026-04-06T10:18:00Z",
  durationSeconds: 506,
  audioSrc: "/sample-call.mp3",
  report: {
    overallScore: 51.3,
    grade: "F",
    severity: "major",
    dimensionScores: {
      script_compliance: 0,
      factual_accuracy: 25,
      politeness_tone: 100,
      empathy: 75,
      conflict_detection: 100,
      issue_resolution: 100,
      overall_severity: 25,
    } as Record<string, number>,
    dimensionWeights: {
      script_compliance: 0.25, factual_accuracy: 0.25, politeness_tone: 0.15,
      empathy: 0.10, conflict_detection: 0.15, issue_resolution: 0.05, overall_severity: 0.05,
    } as Record<string, number>,
    dimensionReports: {
    script_compliance: "The agent failed to follow several critical protocols, including closing the call, disclosing the change and billing impact, obtaining authorization for the change, escalating the issue to a supervisor, following the hold protocol, using prohibited language, transferring the customer to the correct department, and verifying the customer's account information.",
    factual_accuracy: "The agent gave inaccurate billing information: the customer was charged $67.81 against a $40 plan, and the agent did not clearly reconcile or correct the discrepancy on the call.",
    politeness_tone: "The agent demonstrates a consistently professional, warm, and courteous tone throughout the call, using polite language and phrases to reassure and appreciate the customer.",
    empathy: "The agent showed empathy in most emotional moments, but missed a few opportunities to acknowledge the customer's feelings. The agent's responses were generally genuine and apologetic.",
    conflict_detection: "The agent effectively de-escalated the customer's frustration and confusion, providing clear explanations and resolving the issue.",
    issue_resolution: "The customer's issue was fully resolved, and they were satisfied with the explanation and solution provided by the agent.",
    overall_severity: "The customer service agent failed to provide accurate information about the plan details, causing confusion and frustration for the customer. The agent also failed to de-escalate the customer's frustration, which led to a negative experience."
  } as Record<string, string>,
    reportJson: {
      summary: "This MetroBoost billing call scored 51.3/100 (grade F, major severity). The agent stayed calm, professional, and empathetic and ultimately resolved the dispute, but gave inaccurate pricing information and skipped required disclosures and the closing script, which drove the score down.",
      strengths: [
    "The agent demonstrates a consistently professional, warm, and courteous tone throughout the call, using polite language and phrases to reassure and appreciate the customer.",
    "The agent effectively de-escalated the customer's frustration and confusion, providing clear explanations and resolving the issue.",
    "The customer's issue was fully resolved, and they were satisfied with the explanation and solution provided by the agent."
  ],
      weaknesses: [
    "The agent failed to follow several critical protocols, including closing the call, disclosing the change and billing impact, obtaining authorization for the change, escalating the issue to a supervisor, following the hold protocol, using prohibited language, transferring the customer to the correct department, and verifying the customer's account information.",
    "The agent gave inaccurate billing information: the customer was charged $67.81 against a $40 plan, and the agent did not clearly reconcile or correct the discrepancy on the call.",
    "The customer service agent failed to provide accurate information about the plan details, causing confusion and frustration for the customer. The agent also failed to de-escalate the customer's frustration, which led to a negative experience."
  ],
      recommended_actions: [
    "Quote billing figures only after confirming them against the customer's plan and current pricing.",
    "Deliver all required disclosures (AutoPay/O2Pay enrolment and cancellation terms) and obtain explicit authorization.",
    "Use the approved closing script before ending every call."
  ],
    },
    evidence: [
  { dimension: "script_compliance", quote: "Oh, you just don't know how happy i am linda thank you for giving me the chance to bring back your trust with us and if you don't have any further questions thank you so much for being the best part of nurture boost", speaker: "Agent", reason: "Closing" },
  { dimension: "script_compliance", quote: "Exactly. Also, I've seen that your credit card is currently not enrolled in O2Pay.", speaker: "Agent", reason: "Disclosure" },
  { dimension: "politeness_tone", quote: "Oh, I'm so sorry about this. I can't blame you if you'll feel that way.", speaker: "Agent", reason: "not met" },
  { dimension: "politeness_tone", quote: "I want to make sure that this will be taken care of today.", speaker: "Agent", reason: "not met" }
] as { dimension: string; quote: string; speaker: string; reason: string }[],
  },
  appeal: {
    status: "Overturned",
    agentReason: "The pricing I quoted came from the plan card I was given at the start of the shift; the corrected figure had not been pushed to us yet.",
    qaResponse: "Confirmed the pricing card was updated mid-shift. Factual-accuracy deduction reduced on human review; the original AI score is preserved for the record.",
    correctedScore: 63,
    submittedAt: "2026-04-07",
  },
  transcript: [
  { role: "Customer Service Agent", start: 2.04, end: 5.40, emotion: null, signals: ["QUESTIONING"], text: "calling Metrobus. This is Chalene. How can I help you today?" },
  { role: "Customer", start: 6.51, end: 21.99, emotion: null, signals: ["QUESTIONING"], text: "tell me. I'm looking at my statement and I see that you guys charged my credit card for $67.81 when I initially signed up for a $40 plan. Guess what? My bank charged me for an overdraft fee." },
  { role: "Customer", start: 22.59, end: 41.22, emotion: null, signals: ["FRUSTRATED"], text: "is ridiculous. If I know that you lied to me, I should have chosen Global Phone instead. Very, very disappointing. I've been with you guys for so many years now. I've started my account in postpaid and decided to switch over prepay, and I want you to cancel my account completely. I don't want to deal with this again." },
  { role: "Customer Service Agent", start: 41.22, end: 45.59, emotion: null, signals: ["APOLOGETIC"], text: "Oh, I'm so sorry about this. I can't blame you if you'll feel that way." },
  { role: "Customer Service Agent", start: 46.17, end: 61.46, emotion: null, signals: [], text: "really surprising that you've been charged $67.81 instead of just $40. It's a huge amount of money, and I want to make sure that this will be taken care of today. By the way, let me have your name so I can address you properly." },
  { role: "Customer", start: 62.97, end: 69.35, emotion: null, signals: [], text: "name is Linda Marone, and you better do something about this today or I'll change carriers." },
  { role: "Customer Service Agent", start: 70.10, end: 74.38, emotion: null, signals: ["SATISFIED"], text: "understand, Linda, and I won't let you go unless and until this is resolved." },
  { role: "Customer Service Agent", start: 74.89, end: 82.26, emotion: null, signals: [], text: "I want to make sure that I'll be able to track all the details of your account so I could come up with the best resolution for you today." },
  { role: "Customer Service Agent", start: 82.90, end: 86.75, emotion: null, signals: ["QUESTIONING"], text: "May I have your mobile number and your four-digit PIN, please?" },
  { role: "Customer", start: 87.27, end: 94.87, emotion: null, signals: [], text: "number is 607-598-6992. PIN is 0903." },
  { role: "Customer Service Agent", start: 97.67, end: 98.29, emotion: null, signals: [], text: "you." },
  { role: "Customer Service Agent", start: 99.10, end: 100.20, emotion: null, signals: [], text: "right, Shiloh." },
  { role: "Customer Service Agent", start: 101.16, end: 116.30, emotion: null, signals: [], text: "was able to pull up your account details. i've seen that you initially traded the account through our MetroBoo store last December the 21st, and the plan that was graded for you was the $65 unlimited plan." },
  { role: "Customer Service Agent", start: 116.77, end: 125.29, emotion: null, signals: [], text: "So, it includes unlimited cost, tax, and data. The additional $2.81 that was charged is coming from the taxes." },
  { role: "Customer", start: 125.53, end: 134.91, emotion: null, signals: ["QUESTIONING"], text: "Wait, so this $65 plan is unlimited? What about the $40? I thought $40 is unlimited. That's what the salesperson told me last" },
  { role: "Customer Service Agent", start: 137.66, end: 177.25, emotion: null, signals: ["APOLOGETIC"], text: "apologize for the confusion. The $40 plan has unlimited costs and checks, but the data is not unlimited. You'll only get 5 gigs of data for $40. At Blender, we have four different plans. We have the $30 plan, the cheapest that we have. It has unlimited calls and texts, but it doesn't have a data on it. Then the $40 plan that has unlimited calls and texts with 5 gigs of data, a $50 plan with unlimited calls and texts and 15 gigabytes of data, and lastly, the $65 plan with unlimited calls, texts, and data." },
  { role: "Customer Service Agent", start: 179.06, end: 189.13, emotion: null, signals: ["QUESTIONING"], text: "me make sure that I understand it correctly. The salesperson told you that the $40 plan has a limited cost tax and data. Is that correct?" },
  { role: "Customer", start: 191.01, end: 202.82, emotion: null, signals: ["CONFUSED"], text: "to be honest with you, I'm not sure. It's telling a bunch of different things. And you don't remember if the $40 plan includes a limited data, but I'm pretty sure it has a limited cost and tax." },
  { role: "Customer Service Agent", start: 204.69, end: 206.02, emotion: null, signals: [], text: "that's all right." },
  { role: "Customer Service Agent", start: 207.61, end: 211.32, emotion: null, signals: ["QUESTIONING"], text: "I may ask, how do you usually use your phone in terms of data?" },
  { role: "Customer", start: 211.46, end: 213.48, emotion: null, signals: [], text: "In terms of data, well," },
  { role: "Customer", start: 214.16, end: 221.25, emotion: null, signals: [], text: "use Facebook a lot. I watch Netflix a lot, check my email, and play some games, too." },
  { role: "Customer Service Agent", start: 222.58, end: 229.23, emotion: null, signals: ["QUESTIONING"], text: "that's quite a lot. So do you you think that the five gigs of data for $40 would be enough for you?" },
  { role: "Customer", start: 229.78, end: 231.79, emotion: null, signals: [], text: "No, I don't think it would" },
  { role: "Customer", start: 232.84, end: 234.83, emotion: null, signals: [], text: "stay with the current plan I have." },
  { role: "Customer Service Agent", start: 235.88, end: 247.37, emotion: null, signals: ["SATISFIED"], text: "Right. This plan is really perfect for you since you've got so many activities that requires data. And with this $65 unlimited plan, you won't need to worry about running out of data." },
  { role: "Customer Service Agent", start: 249.56, end: 258.40, emotion: null, signals: ["QUESTIONING"], text: "to confirm, you'd like to stay with your $65 unlimited plan. So I'll keep it as it is for you. No changes should be made, correct?" },
  { role: "Customer", start: 258.79, end: 259.47, emotion: null, signals: [], text: "right." },
  { role: "Customer Service Agent", start: 260.29, end: 261.56, emotion: null, signals: [], text: "righty. So do" },
  { role: "Customer Service Agent", start: 261.96, end: 264.18, emotion: null, signals: ["QUESTIONING"], text: "have any other questions for me today?" },
  { role: "Customer", start: 264.85, end: 272.98, emotion: null, signals: ["QUESTIONING"], text: "Jalene. So, I'll pay $65 per month for the unlimited plan and $2.81 for the taxes, correct?" },
  { role: "Customer Service Agent", start: 274.06, end: 317.94, emotion: null, signals: [], text: "that's correct, Linda. Expect no other charges in your account every month aside from the $67.81. And by the way, I have a good for you. I understand that you've been with us for so many years now. You started your account with postpaid and switched over prepaid. So the goodness about it is once you've reached your third month with us, your next bill will have a $5 discount on it. So instead of paying $65 for the plan, it'd only be $60. And once you've reached your ninth month with prepaid, you'll get an additional $5 discount. So instead of paying $60, you'll only need to pay $55." },
  { role: "Customer", start: 318.73, end: 323.32, emotion: null, signals: [], text: "that's awesome. This is a lot cheaper than what I've paid before in Postpay." },
  { role: "Customer Service Agent", start: 323.59, end: 329.50, emotion: null, signals: [], text: "Exactly. Also, I've seen that your credit card is currently not enrolled in O2Pay." },
  { role: "Customer Service Agent", start: 329.92, end: 354.49, emotion: null, signals: [], text: "I'm glad to let you know that if you decided to enroll your credit card in O2Pay, you'll get an additional $5 discount on your bill every month. So let's say you decided to enroll your credit card in O2Pay today, you'll automatically get the $5 discount on your next billing cycle. So instead of paying $67.81, you'll only need to pay $62.81." },
  { role: "Customer", start: 354.81, end: 356.01, emotion: null, signals: ["QUESTIONING"], text: "Oh, seriously?" },
  { role: "Customer Service Agent", start: 356.65, end: 359.45, emotion: null, signals: [], text: "All right. Do you have the Metraboost app on your" },
  { role: "Customer", start: 360.67, end: 363.03, emotion: null, signals: [], text: "Yes, I do. I downloaded it last time." },
  { role: "Customer Service Agent", start: 363.82, end: 366.35, emotion: null, signals: [], text: "Kylie, tap that app for me." },
  { role: "Customer Service Agent", start: 367.94, end: 371.82, emotion: null, signals: [], text: "in with your Metro Boost account. Yes, I do. I downloaded it last time. Awesome. Kylie, tap that app for me. Log in with your Metro Boost account and let me know once you're in the homepage," },
  { role: "Customer", start: 375.43, end: 376.38, emotion: null, signals: [], text: "I'm in." },
  { role: "Customer Service Agent", start: 376.90, end: 383.75, emotion: null, signals: ["QUESTIONING"], text: "right. So, on the upper left corner, you'll see the hamburger icon or the three horizontal lines, correct?" },
  { role: "Customer", start: 384.58, end: 385.51, emotion: null, signals: [], text: "Yes, I see it. it" },
  { role: "Customer Service Agent", start: 387.63, end: 388.65, emotion: null, signals: [], text: "that for me" },
  { role: "Customer", start: 390.96, end: 398.94, emotion: null, signals: [], text: "right now i see feed data checker payment account my devices shop now and sign out" },
  { role: "Customer Service Agent", start: 400.64, end: 401.93, emotion: null, signals: [], text: "now click on payment" },
  { role: "Customer", start: 402.79, end: 410.89, emotion: null, signals: [], text: "now it says your next payment is due in 27 days. Available balance is zero. Then below it says Add Funds." },
  { role: "Customer Service Agent", start: 410.89, end: 415.22, emotion: null, signals: ["QUESTIONING"], text: "And below Add Funds, have you seen the option to turn on the AutoPay?" },
  { role: "Customer", start: 416.66, end: 417.64, emotion: null, signals: [], text: "yeah, I do." },
  { role: "Customer Service Agent", start: 419.21, end: 428.34, emotion: null, signals: [], text: "right. So if you're ready to set up your AutoPay today, you'll just need to turn on the2Pay option, key in your credit card information, and save it." },
  { role: "Customer", start: 428.35, end: 435.76, emotion: null, signals: [], text: "Okie dokie. I'll add it later because I'm not at home right now, and I'll be using a different card for the O2Pay." },
  { role: "Customer Service Agent", start: 437.14, end: 441.62, emotion: null, signals: [], text: "Okay, not a problem. You already know the steps, so it'll be easy for you." },
  { role: "Customer", start: 442.85, end: 446.48, emotion: null, signals: ["SATISFIED"], text: "Exactly. Well, thank you so much for letting me know all this good stuff." },
  { role: "Customer Service Agent", start: 447.81, end: 466.86, emotion: null, signals: ["SATISFIED","QUESTIONING"], text: "welcome, Linda. And I appreciate you partnering with me today to make sure that everything is clear in terms of your plan details. And I'm glad that I was able to give you a walkthrough on how to set up O2Pay so you can take advantage of the discount that comes with it., would there be anything else that I could further assist you with today?" },
  { role: "Customer", start: 467.16, end: 475.82, emotion: null, signals: ["SATISFIED"], text: "No, honey, you've been very helpful. You bring back the confidence that I have with Metraboost that I thought I lost when I started getting those unexplainable charges, but" },
  { role: "Customer", start: 476.28, end: 482.12, emotion: null, signals: [], text: "made everything so clear for me, and now we understand how the plan works, and I don't have any further questions." },
  { role: "Customer Service Agent", start: 482.39, end: 496.00, emotion: null, signals: ["SATISFIED"], text: "Oh, you just don't know how happy i am linda thank you for giving me the chance to bring back your trust with us and if you don't have any further questions thank you so much for being the best part of nurture boost" },
  { role: "Customer Service Agent", start: 496.53, end: 497.22, emotion: null, signals: [], text: "a good one" },
  { role: "Customer", start: 499.08, end: 500.36, emotion: null, signals: [], text: "too dear bye" }
] as SampleTurn[],
};
