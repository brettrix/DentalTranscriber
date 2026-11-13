# Held-Out Test Cases (Cases 4–8)

All five held-out limited exams for the final evaluation. **All patients are made up.** Claude Code must not open this file until the held-out run (stage 9).

- Cases 4–6: written with the original scripts.
- Cases 7–8: curveball cases written by Claude (the same assistant that wrote the build prompt) in place of a teammate's cases. Note this in the report.

Tooth numbers use the Universal system: #3 = upper right first molar, #8 = upper right front tooth, #9 = upper left front tooth, #12 = upper left first premolar, #17 = lower left wisdom tooth, #19 = lower left first molar, #30 = lower right first molar.

---

## Case 4: Sore, bleeding gums, upper right (HELD OUT)

**Quick notes**
```
BP 128/78
CC: gums sore + bleeding upper right
#3
```

**Script**

DENTIST: Hi, what brings you in?
PATIENT: My gums in the upper right are sore, and they bleed every time I brush. It's been like that for a couple months.
DENTIST: Any pain in the tooth itself, like with cold or biting?
PATIENT: Not really, it's more the gums. Sometimes there's a bad taste.
DENTIST: When was your last cleaning?
PATIENT: Honestly, it's been maybe three years.
DENTIST: No judgment. Any health changes or new meds?
PATIENT: No.
DENTIST: Okay, let's look. Around number three the gums are red and puffy. I'm going to measure the pockets. Distal buccal six, buccal four, mesial buccal seven. Bleeding on probing. Lingual, five, four, six. Lots of bleeding.
ASSISTANT: Got it.
DENTIST: Plaque is moderate today. Can we get a bitewing on the right side?
ASSISTANT: Bitewing taken.
DENTIST: The bitewing shows calculus on the roots of three and some bone loss around it. No decay that I can see.
PATIENT: What does that mean?
DENTIST: You've got gum disease, periodontitis, in that area. The tartar has gone under the gumline, and the gums have pulled away from the tooth, making these deeper pockets. A regular cleaning won't reach that. You need a deep cleaning, scaling and root planing, in that upper right quadrant.
PATIENT: Does that hurt?
DENTIST: We numb you, so it's comfortable. Afterward you might be a little sore for a day or two. If we don't treat it, the bone keeps going away and eventually the tooth can get loose.
PATIENT: Okay, let's do it.
DENTIST: Great. We'll schedule scaling and root planing, upper right quadrant. I'll also send in a chlorhexidine rinse, use it twice a day for two weeks. And floss daily, even if it bleeds at first.
PATIENT: Okay.

**Answer key**
- Tooth/area: #3, upper right quadrant
- Required facts:
  1. Chief complaint: sore, bleeding gums upper right for a couple months; occasional bad taste
  2. No tooth pain with cold or biting
  3. Last cleaning about 3 years ago
  4. No medical changes; BP 128/78
  5. Gums red and swollen around #3
  6. Probing depths #3: buccal 6-4-7, lingual 5-4-6, with bleeding on probing
  7. Bitewing: calculus on the roots of #3, bone loss, no decay
  8. Diagnosis: periodontitis, upper right / #3
  9. Recommended: scaling and root planing (SRP), upper right quadrant; risk of tooth loosening if untreated
  10. Patient accepted
  11. Rx: chlorhexidine rinse twice daily for 2 weeks
  12. Home care: floss daily
- Forbidden facts: none
- Expected flags: **none.** Probing depths, bleeding, calculus, and bone loss are all documented, so the `perio_rationale` review question should *not* fire. The note should record "moderate plaque" exactly as the dentist said it. This case tests that the system doesn't push for stronger wording.
- Expected decision: accepted

---

## Case 5: Chipped front tooth, spouse present (HELD OUT)

Three speakers: DENTIST, PATIENT, and OTHER (the patient's spouse).

**Quick notes**
```
BP 118/76
CC: chipped front tooth, fell off bike
#9
```

**Script**

DENTIST: Oh no, what happened?
PATIENT: I fell off my bike yesterday and hit my mouth on the handlebar. Chipped my right front tooth.
OTHER: He was going way too fast.
DENTIST: Ha. Did you hit your head, or pass out at all?
PATIENT: No, just my mouth.
DENTIST: Any pain?
PATIENT: It's a little sensitive to air and cold, but not bad. Maybe a three.
DENTIST: Any health changes or medications?
PATIENT: No.
DENTIST: Okay, let's take a look. Number eight has a fracture of the biting edge. It's through the enamel and into some dentin, but I don't see any pink or bleeding, so the nerve isn't exposed. Lips and gums look fine, just a small cut on the inside of the upper lip.
DENTIST: Tapping on eight. Okay? And cold.
PATIENT: Cold's a little sensitive but goes away.
DENTIST: Good. The tooth isn't loose. Let's get a PA of the front teeth to check the roots.
ASSISTANT: Taking it now.
DENTIST: The roots of eight and nine look good, no root fracture.
OTHER: So can it be fixed? Is it going to need a crown?
DENTIST: It's very fixable. We can bond tooth-colored filling material onto it to rebuild the edge. That's called composite bonding. No crown needed right now.
PATIENT: Can we do that soon? I've got a wedding in two weeks.
DENTIST: We'll get you in next week to bond number nine. Until then, avoid biting into hard things with your front teeth. Sometimes after an injury the nerve can get irritated later, so if it turns gray or starts to hurt on its own, call us.
OTHER: How much will that be?
DENTIST: The front desk can go over cost with you on the way out.
PATIENT: Okay, thanks.

**Answer key**
- Tooth: #8 (upper right central incisor; "right front tooth," and the dentist examined #8)
- Required facts:
  1. Chief complaint: chipped right front tooth from a bike fall yesterday
  2. No head injury or loss of consciousness
  3. Mild sensitivity to air and cold, 3/10
  4. No medical changes; BP 118/76
  5. Fracture of the incisal edge of #8, enamel and dentin, no pulp exposure
  6. Small cut on the inner upper lip; gums fine
  7. Percussion negative; cold sensitive but not lingering; not mobile
  8. PA: roots of #8 and #9 intact, no root fracture
  9. Diagnosis: enamel-dentin fracture (uncomplicated crown fracture), #8
  10. Treatment: composite bonding; no crown needed now
  11. Patient accepted; scheduled next week
  12. Instructions: avoid biting hard things with front teeth; call if the tooth turns gray or hurts on its own
- Forbidden facts: the wedding should not appear as a clinical fact (it's fine as context for scheduling, but not required)
- Expected flags: **treatment vs. findings tooth disagreement (high)**: the findings and diagnosis are on #8, but the next-visit treatment is "bond number nine." Also a **quick-note tooth question (medium)**: the quick note has an unlabeled "#9," which doesn't match the clinical target #8.
- Expected decision: accepted

---

## Case 6: Wisdom tooth pain, chatty patient, high blood pressure (HELD OUT)

**Quick notes**
```
BP 172/104
CC: back lower left gum hurts, hard to open
#17
```

**Script**

DENTIST: Hi, how are you doing?
PATIENT: Oh, you know, hanging in there. We just got back from Moab, did the Delicate Arch hike, it was amazing, but my mouth started hurting halfway through the trip, which kind of ruined it.
DENTIST: Sorry to hear that. Where does it hurt?
PATIENT: Way in the back on the lower left. The gum is swollen and it hurts to open wide. My wife thinks it's my wisdom tooth.
DENTIST: How long?
PATIENT: About five days. We were camping, so I just kept taking Advil. My brother-in-law had his wisdom teeth out and said it was the worst week of his life, so I've been avoiding it.
DENTIST: Pain level?
PATIENT: Like a six.
DENTIST: Okay. Any health changes or medications? I see your blood pressure was 172 over 104 today.
PATIENT: Huh. I haven't been to the doctor in a while. Maybe it's the stress from the trip.
DENTIST: Let's recheck it in a few minutes. Let me take a look. Number seventeen is partly through the gum, and the gum flap over it is red and swollen. A little tender when I press. You can open about two fingers wide.
ASSISTANT: Rechecked the blood pressure, 168 over 102.
DENTIST: Thanks. Still high. Let's get a pano so I can see how the wisdom tooth is sitting.
ASSISTANT: Pano is up.
DENTIST: Seventeen is impacted and tilted forward, pushing toward eighteen. There's no decay on eighteen. This is an infection of the gum around a partially erupted wisdom tooth. It's called pericoronitis.
PATIENT: So it has to come out?
DENTIST: Yes, I'd recommend having seventeen removed. Because of how it's angled, I'd like an oral surgeon to do it, so I'll refer you. For now: warm salt water rinses several times a day, and ibuprofen 600 milligrams every six hours as needed. Since your blood pressure is high today, please see your primary care doctor before the surgery. The surgeon will want that checked.
PATIENT: Okay, that's fair. Do you know any good surgeons?
DENTIST: The front desk will send the referral over today.
PATIENT: Great. Have you ever been to Moab?
DENTIST: A long time ago. Go see your doctor, okay?

**Answer key**
- Tooth: #17
- Required facts:
  1. Chief complaint: pain and swelling in the back lower left gum, hard to open wide, about 5 days
  2. Taking Advil (ibuprofen) on their own
  3. Severity 6/10
  4. BP 172/104, rechecked at 168/102; hasn't seen a doctor in a while
  5. #17 partially erupted; gum flap red, swollen, and tender; opening about two fingers
  6. Pano: #17 impacted and tilted forward toward #18; no decay on #18
  7. Diagnosis: pericoronitis, #17
  8. Recommended: extraction of #17 by an oral surgeon (referral)
  9. Patient accepted the referral
  10. Home care: warm salt water rinses; ibuprofen 600 mg every 6 hours as needed
  11. Advised to see their primary care doctor about blood pressure before surgery
- Forbidden facts: Moab, Delicate Arch, camping, the brother-in-law's story, the wife's opinion
- Expected flags: **elevated blood pressure (medium)**: 172/104, rechecked 168/102. The recheck and doctor referral are documented, so this is informational, not missing.
- Expected decision: accepted (referral)

---

## Case 7: Wrong side, then a change of plan (HELD OUT)

Curveballs: the patient corrects which side hurts, the dentist changes the plan after the x-ray, the patient answers with "mm-hmm," a discontinued medication, and a quick note written before the patient corrected herself.

**Quick notes**
```
BP 126/82
CC: lower right pain
#30
Meds: none
```

**Script**

DENTIST: Hi, what's going on today?
PATIENT: I've got a toothache on the lower right. It's been bugging me for about a week.
DENTIST: Okay. Does anything set it off?
PATIENT: Cold stuff, and sometimes it just starts hurting by itself at night. Wait, actually, sorry. It's the left side. Lower left. I always mix those up.
DENTIST: No problem. Lower left. Point to it for me?
PATIENT: Mm-hmm. Right there.
DENTIST: Okay, that's number nineteen. When cold hits it, how long does the pain last?
PATIENT: A while. Maybe twenty seconds, it kind of throbs after.
DENTIST: Scale of zero to ten?
PATIENT: When it wakes me up, an eight.
DENTIST: Any changes to your health or medications?
PATIENT: I used to be on warfarin, the blood thinner, but my doctor took me off it last year. Nothing now.
DENTIST: Good to know, thanks. Let's look. There's a big cavity on the back side of nineteen. Honestly, this might just need a filling. Let me test it. Cold on nineteen.
PATIENT: Ow. Yeah. That's still going.
DENTIST: Still lingering?
PATIENT: Mm-hmm.
DENTIST: Okay. Tapping?
PATIENT: A little tender.
DENTIST: Let's get a PA of nineteen.
ASSISTANT: PA of nineteen is up.
DENTIST: Okay, I'm changing my mind on the filling. The decay goes right down to the nerve. With the pain lasting that long and waking you up at night, the nerve is inflamed and isn't going to recover. That's irreversible pulpitis. A filling won't fix it.
PATIENT: So what do I do?
DENTIST: The best option is a root canal, and then a crown to protect the tooth afterward. The other option is taking the tooth out. That's quicker, but then you'd have a gap, and the teeth around it can shift over time.
PATIENT: Are there risks with the root canal?
DENTIST: It's a very common procedure. Sometimes the tooth needs retreatment down the road, and without a crown it can crack. But it lets you keep your tooth.
PATIENT: Okay. Let's do the root canal.
DENTIST: Great. We'll get you in this week for the root canal on nineteen, then the crown a few weeks after. For pain until then, ibuprofen, six hundred milligrams every six hours as needed.
PATIENT: Thank you.

**Answer key**
- Tooth: #19 (lower left first molar). The patient first said lower right, then corrected to lower left.
- Required facts:
  1. Chief complaint: toothache, about 1 week, lower LEFT (after self-correction from lower right)
  2. Triggers: cold; also spontaneous night pain
  3. Cold pain lingers about 20 seconds; severity 8/10 when it wakes her
  4. Medication: warfarin discontinued last year; no current medications
  5. BP 126/82
  6. Large cavity on the distal/back side of #19
  7. Cold test on #19: positive and lingering; percussion mildly tender
  8. PA of #19: decay extends to the pulp
  9. Diagnosis: irreversible pulpitis, #19
  10. Initial impression of a filling was changed after the x-ray (the final plan is not a filling)
  11. Options: root canal + crown (recommended), or extraction (with the risk of a gap and shifting teeth)
  12. Risks of root canal discussed: possible retreatment, cracking without a crown
  13. Patient accepted root canal
  14. Next visit: root canal on #19 this week, crown a few weeks later
  15. Rx: ibuprofen 600 mg every 6 hours as needed
- Forbidden facts: warfarin listed as a current medication; a filling listed as the treatment plan; any treatment on #30 or the lower right
- Expected flags:
  - **Self-correction conflict (medium or high):** "lower right" vs. "lower left," with the later statement (left) identified
  - **Quick-note complaint mismatch (low):** quick note says "CC: lower right pain," but the corrected complaint is lower left
  - **Unlabeled quick-note tooth (medium):** quick note "#30" matches neither the complaint location nor the clinical target #19
  - No `refusal_discussion` (treatment accepted); no `allergy_rx`
- Expected decision: accepted

---

## Case 8: Declined crown, quick-note BP mismatch, Spanish phrase (HELD OUT)

Curveballs: a phrase in Spanish, a reported-resolved allergy, a quick-note BP that doesn't match what was said, no new x-ray needed, and a recommended crown declined without the dentist explaining the risks.

**Quick notes**
```
BP 162/98
CC: broken filling upper left
#12
Allergy: penicillin?
```

**Script**

DENTIST: Hi there, what brings you in?
PATIENT: A piece of my filling broke off on the top left. Y me duele cuando como dulces. Sorry, it hurts when I eat sweets.
DENTIST: No worries. When did it break?
PATIENT: Like four days ago, eating a granola bar.
DENTIST: Does it hurt with cold, or when you bite?
PATIENT: Not really cold. Mostly sweets, and a little when I bite on it.
DENTIST: Okay. Your blood pressure was one twenty-eight over eighty-four today, that looks good. Any allergies?
PATIENT: I was allergic to penicillin as a kid, I think. But I've taken amoxicillin since then with no problem.
DENTIST: Okay, we'll note that. Any changes to your health?
PATIENT: Nope.
DENTIST: Let's take a look. Number twelve, the old filling has a big piece missing on the side, and there's a crack running through what's left of the tooth. Bite on this for me.
PATIENT: Ooh, a little sharp.
DENTIST: Okay. We don't need a new x-ray. The bitewings from your cleaning last month show this area, and there's no decay near the nerve.
PATIENT: Okay, good.
DENTIST: Because so much of the tooth is gone and it's cracked, I'd recommend a crown on twelve. A filling probably won't hold.
PATIENT: How much is a crown?
DENTIST: The front desk can give you an exact estimate.
PATIENT: Honestly, money's tight right now. I don't think I'm going to do it.
DENTIST: Okay, that's fine. Just let us know if you change your mind.
PATIENT: Will do. Gracias.

**Answer key**
- Tooth: #12 (upper left first premolar)
- Required facts:
  1. Chief complaint: broken filling, upper left, about 4 days ago, broke on a granola bar
  2. Pain with sweets (also said in Spanish) and slightly when biting; no notable cold sensitivity
  3. BP 128/84, as stated by the dentist
  4. Allergy: penicillin as a child, reported resolved (has taken amoxicillin since without problems)
  5. No health changes
  6. #12: large piece of old filling missing; crack through the remaining tooth
  7. Bite test: mildly sharp
  8. No new x-ray needed; bitewings from last month show no decay near the nerve
  9. Recommended: crown on #12 (a filling likely won't hold)
  10. Patient declined due to cost
  11. Consequences of declining were NOT explained
- Forbidden facts: BP 162/98 presented as confirmed or as the only reading; "informed refusal discussed"; an active, unqualified penicillin allergy; a new radiograph taken
- Expected flags:
  - **Quick-note vs. transcript BP conflict (medium):** quick note says 162/98, the dentist said 128/84; both readings kept
  - **BP reading (medium, precautionary):** the 162/98 quick-note reading meets Level A and depends on unconfirmed information
  - **Refusal discussion question (low):** a recommended crown was declined with no consequences-of-refusal discussion
  - No `radiograph_finding_missing` (a new x-ray was "not needed"); no `allergy_rx` (no prescription)
- Expected decision: declined
