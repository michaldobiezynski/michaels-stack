---
name: langchain-academy-lesson-content-in-repo
description: |
  Get LangChain Academy lesson content (labs, quizzes, homework) when the
  academy.langchain.com lesson URL is auth-gated. Use when: (1) WebFetch of an
  academy.langchain.com/courses/take/... URL returns only a sign-in/registration
  page, (2) the user asks for help with a LangChain Academy lesson, lab, or
  homework, (3) you need to map an academy URL slug like
  "lesson-2-local-deployment" to actual course files. The course's GitHub repo
  (e.g. langchain-ai/lca-deepagents) mirrors the FULL lesson text under
  thinkific/src/, and a public GitHub Pages mirror exists at
  langchain-ai.github.io/lca-lessons/.
author: Claude Code
version: 1.0.0
date: 2026-08-25
---

# LangChain Academy Lesson Content Lives in the Course Repo

## Problem

LangChain Academy lesson pages (Thinkific-hosted) require login; WebFetch gets
only the sign-in page. The lesson pages carry the lab and homework instructions,
so without them you cannot set up or teach the lesson.

## Context / Trigger Conditions

- WebFetch of `academy.langchain.com/courses/take/...` returns an
  authentication form instead of content.
- User references a lesson by academy URL, e.g.
  `.../multimedia/75788613-lesson-2-local-deployment`.

## Solution

1. Find the course's GitHub repo (linked from the course description; for the
   Deep Agents course it is `langchain-ai/lca-deepagents`). Check
   `~/development/projects/` first - the user may already have a clone/fork.
2. Full lesson source (lesson text + Lab + Quiz + Homework tabs, all in one
   markdown file) lives at `thinkific/src/mX/mX.Y-<slug>.md` in that repo.
3. Slug mapping gotcha: the academy URL says "lesson-2-..." but that is the
   lesson number WITHIN a module. Match the slug text against filenames, not
   the number: `lesson-2-local-deployment` -> `m5.2-local-deployment.md`
   (module 5, lesson 2).
4. No clone at hand? The first line of each lesson file links a public mirror:
   `https://langchain-ai.github.io/lca-lessons/<course>/mX/mX.Y-<slug>.html`
   - fetchable without auth.
5. Lab/homework code the lesson references lives in the same repo under
   `python/mX/` and `typescript/mX/`.

## Verification

Verified 25/08/2026: m5.2 Local Deployment lesson, lab, quiz, and homework all
read from `thinkific/src/m5/m5.2-local-deployment.md`; lab ran successfully
from `python/m5/hello/`.

## Notes

- Keep a fork current with `git fetch upstream && git merge --ff-only
  upstream/main` (upstream pushes are disabled on course forks; content
  updates are frequent).
- The Python course pins exact dependency versions (e.g. `deepagents==0.7.0`);
  resync with `uv sync` after pulling rather than upgrading ad hoc.
