# Learning a new stack with AI + documentation

You'll be learning at least one new technology for this project (React, Go, Earth Engine, PostGIS…). AI makes this much faster, **if** you use it as a tutor instead of a code vending machine. This page is the method; your section guide lists the specific tools and official docs.

---

## The 5-step method (per tool, ~1–3 days)

### 1. Get the mental model first (30 min)
Before any code, ask for the *idea*:
```text
I'm a CS student who knows <Python/Java/…>. Explain <tool> as if I'm new to it:
what problem does it solve, what are its 5 core concepts, and how does it compare to <thing I know>?
Use a small analogy. Keep it under 300 words.
```
Then open the **official docs** link from your section guide and skim the "Getting started" or "Tutorial" page. If the AI and the docs disagree, **the docs win**.

### 2. Build a tiny toy, outside the project (1–2 h)
Make a throwaway folder and build the smallest thing that uses the tool. Your section guide gives a practice exercise for each tool. Ask the AI to *guide* you, not to do it:
```text
Guide me through building <exercise> step by step. Give me one step at a time, and wait
for me to say "done" before the next. Don't show the full solution.
```

### 3. Predict, then run
Before running anything, write down what you expect to happen. Then run it. Being wrong is where the learning happens. Ask:
```text
I expected <X> but got <Y>. Explain why, and what concept I misunderstood.
```

### 4. Read real code in our repo
Once the lead's scaffolding exists, open the files in your section and ask:
```text
Walk me through <file>. For each function: what it does, why it's written this way,
and which docs page explains the feature it uses.
```

### 5. Teach it back
Explain the concept to the AI in your own words and ask it to find gaps:
```text
Here's my explanation of <concept>: "<your words>". What's wrong or missing?
Ask me 3 quiz questions to check I understand.
```

---

## Keep a learning log

Create `learning-log.md` in your own notes (not in the repo) and add, each day:
- One thing you learned
- One thing that confused you, and how you resolved it
- One docs link that was actually useful

It takes 3 minutes a day, and it's gold when you write your demo notes or your résumé.

## Good habits

- **Docs first for facts, AI first for explanations.** Function names, options and versions come from the docs. The "why" can come from the AI.
- **Check versions.** Tell the AI which version you use (e.g. "Go 1.23", "React 19"). Old tutorials cause a lot of bugs.
- **Small questions beat huge ones.** "How do I read one row with pgx?" works better than "build my API".
- **Say what you already tried.** Paste the command, the full error and what you expected.
- **Never paste secrets** (API keys, `.env`) into any AI tool.

## When to stop learning and start building

When you can do the practice exercise for each tool in your section **without** the AI writing the code, move to your first ticket. You'll keep learning as you build. That's normal.
