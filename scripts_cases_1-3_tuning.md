# Role-Play Scripts: Cases 1–3 (for building)

Six fake limited-exam appointments to record and test the prototype with. **All patients are made up.**

- **Cases 1–3 are for building.** Give these to Claude Code while it builds and tunes.
- **Cases 4–6 are held out.** Record them, but don't show them or their answer keys to Claude Code until the final test. They're your "cases you didn't design for."
- **Cohen's curveballs:** Cohen writes 2 more cases on his own, without showing Brett, using the tips at the bottom.

## How to record

- Use a phone voice memo in a quiet room, with the phone on the table between you.
- One of you reads DENTIST (and ASSISTANT); the other reads PATIENT. For case 5, which has a third speaker, use a different voice or grab a friend.
- Read naturally. Small ad-libs are fine and realistic. If you ad-lib a clinical detail, update the answer key.
- Save each recording as `case1.m4a`, `case2.m4a`, and so on.
- Type the **Quick notes** into the app's quick-notes box. They're what the assistant would have jotted on the sticky note.
- Don't read the answer keys out loud. They're for scoring.

Tooth numbers use the Universal system: #3 = upper right first molar, #8 = upper right front tooth, #9 = upper left front tooth, #14 = upper left first molar, #17 = lower left wisdom tooth, #19 = lower left first molar, #30 = lower right first molar.

---

## Case 1: Cold sensitivity, upper left (tuning)

**Quick notes**
```
BP 124/80
CC: upper left hurts with cold drinks
#14
No med changes, no allergies
```

**Script**

DENTIST: Hi, I'm Dr. Hale. What brings you in today?
PATIENT: Hey. So my upper left side has been really sensitive to cold. Like when I drink ice water it zings.
DENTIST: How long has that been going on?
PATIENT: Maybe three weeks? It's been getting a little worse.
DENTIST: When the cold hits it, does the pain go away right away, or does it hang around?
PATIENT: It goes away pretty fast. Maybe five seconds.
DENTIST: Okay. Does it ever wake you up at night, or hurt on its own without anything triggering it?
PATIENT: No, only with cold.
DENTIST: Any pain when you bite down?
PATIENT: Not really.
DENTIST: On a scale of zero to ten, how bad is it when it happens?
PATIENT: Like a four.
DENTIST: Okay, let's take a look. Any changes to your health or medications since we last saw you?
PATIENT: Nope, same as before.
DENTIST: Great. So I'm looking at number fourteen. There's an older silver filling here, MO. I can see some dark staining along the edge of it. I'm going to tap on it. Anything?
PATIENT: No.
DENTIST: Now some cold on number fourteen.
PATIENT: Yeah, that's the one.
DENTIST: And it's going away?
PATIENT: Yeah, it's gone.
DENTIST: Good, it went away quickly. Let's get a PA of fourteen.
ASSISTANT: Taking a PA now.
DENTIST: Okay, on the x-ray I can see decay underneath the old filling on the mesial side. It's not close to the nerve, and the root tips look healthy, no infection.
PATIENT: So what does that mean?
DENTIST: It means the nerve is irritated but healthy. We call that reversible pulpitis. If we take out the old filling and the decay underneath it and put in a new tooth-colored filling, it should calm right down.
PATIENT: Okay. Do I need a crown?
DENTIST: Not right now. The tooth has enough structure left for a filling. If we wait, the decay will keep growing and could reach the nerve, which would mean a root canal.
PATIENT: Okay, let's do the filling.
DENTIST: Great. We'll schedule you for next week to replace the MO filling on fourteen with a composite. Until then, try a sensitivity toothpaste and avoid really cold drinks on that side.
PATIENT: Sounds good. Oh, and is it supposed to snow this weekend? I'm trying to go skiing.
DENTIST: I heard maybe up the canyon. Have fun.

**Answer key**
- Tooth: #14
- Required facts:
  1. Chief complaint: cold sensitivity, upper left
  2. Onset about 3 weeks ago, getting worse
  3. Pain lingers about 5 seconds; no spontaneous or night pain; no pain on biting
  4. Severity 4/10
  5. No medical history or medication changes
  6. BP 124/80
  7. Existing MO amalgam (silver filling) on #14 with staining at the margin
  8. Percussion negative; cold test positive, not lingering
  9. PA of #14: recurrent decay under the filling on the mesial, not near the pulp; no periapical pathology
  10. Diagnosis: reversible pulpitis, #14 (recurrent decay)
  11. Options discussed: replace with composite filling; crown not needed now; risk of root canal if delayed
  12. Patient accepted
  13. Next visit: next week, replace MO filling on #14 with composite
  14. Home instructions: sensitivity toothpaste, avoid cold on that side
- Forbidden facts: skiing, snow, the weekend
- Expected flags: **none** (this case tests false alarms)
- Expected decision: accepted

---

## Case 2: Pain on biting, lower right (tuning)

**Quick notes**
```
BP 138/86
CC: sharp pain chewing, lower right
#30
Meds: lisinopril
```

**Script**

DENTIST: Hi, what's going on today?
PATIENT: When I chew on my lower right side, I get this sharp pain. Mostly with harder foods, like nuts.
DENTIST: When did that start?
PATIENT: About a month ago. I bit down on a popcorn kernel and it's been weird since.
DENTIST: Is it a quick sharp pain when you bite, or more of a constant ache?
PATIENT: Quick and sharp. Sometimes when I let go of the bite, too.
DENTIST: Any sensitivity to cold or hot?
PATIENT: A little to cold, but it goes away.
DENTIST: How bad, zero to ten?
PATIENT: When it happens, a seven. Otherwise it's fine.
DENTIST: Any changes to your health or meds?
PATIENT: I started a blood pressure medication a couple months ago. Lisinopril.
DENTIST: Okay, thanks, we'll update that. Let's look. This is number thirty. It has a big old filling. I'm going to have you bite on this little tool, one cusp at a time. Tell me if anything hurts.
PATIENT: Okay. Nothing. Nothing. Ow, that one.
DENTIST: That's the distal lingual cusp of thirty. And when you release?
PATIENT: Yeah, that hurts too.
DENTIST: Okay. Cold test on thirty.
PATIENT: Feel it, it's going away.
DENTIST: Normal response. Tapping? Nothing?
PATIENT: Nothing.
DENTIST: Let's grab a PA of thirty.
ASSISTANT: Got it.
DENTIST: The x-ray looks normal: no decay under the filling and the root tips are healthy. With pain on biting and releasing on that one cusp, this looks like a cracked tooth. Cracks usually don't show up on x-rays.
PATIENT: Is that bad?
DENTIST: It's common, especially with big old fillings. The best treatment is a crown. It holds the tooth together so the crack doesn't spread.
PATIENT: How much is a crown? I'm not sure my insurance covers much this year.
DENTIST: The front desk can give you an estimate. I do want you to know that if we wait, the crack can grow into the nerve. Then you might need a root canal, and if it splits down the root, we'd have to take the tooth out.
PATIENT: Okay, I understand. I want to check my insurance first and maybe do it in January.
DENTIST: That's your call. Until then, try to chew on the other side and avoid hard foods like nuts and ice. If it starts hurting on its own or wakes you up, call us right away.
PATIENT: Okay, will do.

**Answer key**
- Tooth: #30
- Required facts:
  1. Chief complaint: sharp pain chewing on the lower right, especially hard foods
  2. Onset about 1 month ago after biting a popcorn kernel
  3. Pain on biting and on release; mild cold sensitivity that doesn't linger
  4. Severity 7/10 when it happens
  5. New medication: lisinopril (blood pressure), started a couple months ago
  6. BP 138/86
  7. Large existing filling on #30
  8. Bite test positive on the distal-lingual cusp of #30, including on release
  9. Cold test normal; percussion negative
  10. PA of #30: no decay, no periapical pathology
  11. Diagnosis: cracked tooth #30
  12. Recommended: crown on #30
  13. Risks of waiting explained: crack can spread, root canal or extraction (informed refusal)
  14. Patient deferred: wants to check insurance, maybe January
  15. Instructions: chew on the other side, avoid hard foods, call if spontaneous or night pain
- Forbidden facts: none
- Expected flags: none. Informed refusal is documented, so the "deferred without refusal" rule shouldn't fire.
- Expected decision: deferred

---

## Case 3: Swelling, lower left (tuning)

**Quick notes**
```
BP 130/84
CC: swelling + throbbing lower left
#19
Allergy: penicillin
```

**Script**

DENTIST: Hi there. I hear you've got some swelling?
PATIENT: Yeah, my lower left jaw started swelling yesterday, and the tooth back there is throbbing. It kept me up last night.
DENTIST: I'm sorry. How long has the tooth been bothering you?
PATIENT: It hurt on and off a few months ago, then it stopped, and now this.
DENTIST: Pain level right now?
PATIENT: An eight.
DENTIST: Any fever?
PATIENT: I don't think so.
DENTIST: Any allergies to medications?
PATIENT: Yes, penicillin. It gives me hives.
DENTIST: Okay, good to know. Any other changes to your health?
PATIENT: No.
DENTIST: Okay. Number nineteen has a big filling and there's swelling in the gum next to it on the cheek side. I'm going to press here.
PATIENT: Ow, yeah, that's tender.
DENTIST: Tapping on nineteen?
PATIENT: Ow. Yes.
DENTIST: Cold on nineteen.
PATIENT: I don't feel anything.
DENTIST: No response to cold. Let's get a PA.
ASSISTANT: PA of nineteen, done.
DENTIST: On the x-ray there's a dark area around the root tips of nineteen. That's infection. The nerve in the tooth has died, and the infection has spread out the end of the root. That's pulp necrosis with an acute apical abscess.
PATIENT: What are my options?
DENTIST: Two main options. One, a root canal to clean out the infection, then a crown to protect the tooth. That saves the tooth. Two, take the tooth out. That's faster and cheaper up front, but then you have a gap, and we'd talk about an implant or bridge later.
PATIENT: I'd really like to save it.
DENTIST: Okay, we'll do the root canal. I'll get you scheduled in the next few days. In the meantime, I'll send in amoxicillin, 500 milligrams three times a day for seven days, to get the swelling down. And you can take ibuprofen, 600 milligrams every six hours as needed for pain.
PATIENT: Okay.
DENTIST: If the swelling spreads toward your eye or down your neck, or you have trouble swallowing or breathing, go to the ER right away.
PATIENT: Got it.

**Answer key**
- Tooth: #19
- Required facts:
  1. Chief complaint: swelling of the lower left jaw since yesterday, throbbing tooth, kept them up at night
  2. History: intermittent pain a few months ago, then stopped
  3. Severity 8/10; no known fever
  4. Allergy: penicillin (hives)
  5. BP 130/84
  6. Large filling on #19; buccal swelling, tender to palpation
  7. Percussion positive; no response to cold
  8. PA of #19: periapical radiolucency at the root tips
  9. Diagnosis: pulp necrosis with acute apical abscess, #19
  10. Options: root canal + crown, or extraction (with implant/bridge later)
  11. Patient accepted root canal
  12. Rx: amoxicillin 500 mg three times a day for 7 days; ibuprofen 600 mg every 6 hours as needed
  13. Next visit: root canal on #19 within a few days
  14. Emergency instructions: ER if swelling spreads toward the eye or neck, or trouble swallowing or breathing
- Forbidden facts: none
- Expected flags: **allergy vs. prescription (high)**: penicillin allergy, amoxicillin prescribed
- Expected decision: accepted
