# Coding with OpenCode (a free AI coding agent)

[OpenCode](https://opencode.ai/docs/) is an open-source AI coding agent that runs in your terminal. It can read the repo, propose a plan, edit files and run commands. We use it because it's free to start and it reads our project rules from `AGENTS.md`.

> **The deal:** the AI can write code *with* you, but you own every line you submit. In review you'll be asked "why does this work?" and "what happens if the data is empty?". If you can't answer, the PR isn't ready.

---

## 1. Install

Pick one (from the [official docs](https://opencode.ai/docs/)):

```bash
# macOS / Linux (Homebrew)
brew install anomalyco/tap/opencode

# Any OS with Node.js installed
npm install -g opencode-ai

# Universal installer (macOS / Linux)
curl -fsSL https://opencode.ai/install | bash
```

On Windows you can use `choco install opencode` or `scoop install opencode`, or the npm command.

## 2. Connect a free model

```bash
cd inland-resilience
opencode
```

Inside OpenCode, type `/connect` and choose **OpenCode Zen**. Zen offers several models marked **Free** for a limited time. The list changes, so pick any current free model. If one is slow or weak at a task, switch and try another.

⚠️ **Privacy:** some free models are free *because* the provider may use your prompts for training. So:
- **Never** paste API keys, the contents of `.env`, service-account files, passwords, or anyone's personal data into the chat.
- Don't ask it to read `.env`. The real `.env` is git-ignored for a reason.

If you have your own paid key (OpenAI, Anthropic, Google, etc.), `/connect` lets you add that provider instead.

## 3. Let it learn the project

The repo has an `AGENTS.md` file at the root with our rules (which app owns what, stay in your paths, no secrets, tests required). OpenCode reads it automatically. **Don't run `/init`** on this repo: it would regenerate that file. The lead maintains it.

At the start of a session, give it your context:

```text
I'm working on Section N (<name>) of this repo. Read AGENTS.md, docs/guides/start-here.md
and docs/sections/0N-<name>.md. Summarise my job in 5 bullet points and list the folders
I'm allowed to change. Don't write any code yet.
```

If its summary is wrong, correct it before going further.

## 4. Plan mode vs Build mode

Press **Tab** to switch modes.

| Mode | What it does | When |
|---|---|---|
| **Plan** | Reads and thinks; it can't change files. | Always first. Understand the task and agree on an approach. |
| **Build** | Edits files and runs commands. | Only after you've read and agreed with the plan. |

## 5. The loop for every ticket

```text
Read the ticket yourself  →  Plan mode: ask for a plan  →  question the plan
   →  Build mode: one small step  →  run it / run tests  →  read the diff
   →  commit  →  next step  →  open a PR
```

1. **Read the ticket yourself first.** Write in your own words what "done" means.
2. **Plan mode.** Paste the ticket's prompt from your section guide. Ask *"what could go wrong?"* and *"which files will you touch?"*.
3. **Question the plan.** Does it stay inside your paths? Does it use the contracts? Does it add libraries we didn't agree on? Push back.
4. **Build in small steps.** "Do step 1 only, then stop." Small steps are easier to understand and to undo.
5. **Run it.** Start the app or run the tests after every step. Don't let it pile up five untested changes.
6. **Read the diff** (`git diff`). If a line confuses you, ask: *"Explain line 42 like I'm new to Go."*
7. **Commit** with a clear message: `git commit -m "feat(s3): validate polygon is inside county"`.
8. Repeat, then open a PR using the template.

## 6. Prompt templates

**Understand code**
```text
Explain what <file or function> does, step by step, for someone who knows Python but is new
to <Go/React/…>. Then tell me which part I'd most likely break if I changed it.
```

**Write a test first**
```text
Write a failing test for: <acceptance criterion>. Use the fixture at <path>.
Don't implement the feature yet.
```

**Implement the smallest thing**
```text
Make only this test pass, with the simplest code that fits AGENTS.md and my section's paths.
Show me the diff and explain each change in one line.
```

**Debug**
```text
Here is the error and the command I ran: <paste>. List 3 likely causes from most to least likely,
and how to confirm each one. Don't change code yet.
```

**Review your own PR**
```text
Review my changes (git diff main) against docs/sections/0N-<name>.md and the definition of done.
List problems by severity. Check the empty-data and provider-failure cases in particular.
```

## 7. Reviewing AI-written code: checklist

Before you open a PR, check every item:

- [ ] I can explain every changed line.
- [ ] It only touches my section's paths (or the owner is tagged).
- [ ] No new library/dependency unless my section guide or the lead approved it.
- [ ] No hard-coded URLs, keys or secrets. Provider URLs live only in `providers.yaml`.
- [ ] Types and field names match `contracts/` exactly (no "close enough" renames).
- [ ] There's a test for the success case **and** for empty data / failure.
- [ ] Tests pass locally.
- [ ] Nothing was deleted "to make tests pass".
- [ ] User-visible data shows source, time and limitations where relevant.

## 8. When the AI is confidently wrong

It will be, sometimes. Common signs:
- It invents a function or option that doesn't exist. **Check the official docs** linked in your guide.
- It "fixes" a failing test by changing the test.
- It rewrites big files you didn't ask about. Undo with `git checkout -- <file>` and ask for a smaller change.
- It adds a new library for something the standard library already does.

When in doubt, ask your pair partner or post in the team chat. Human review is part of the process, not a sign you did something wrong.
