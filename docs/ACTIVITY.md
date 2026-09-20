# Smart Cache Layer — Guided Activity

**Course:** Advanced Python Programming | ALU BSE
**Topic:** Caching
**Duration:** ~30 minutes
**File to work in:** `blog/views.py`

---

## Overview

we have been given a working Django REST API for a blog platform with 500 posts
and 3 users. The API works — but it hits the database on **every single request**.

Our job was to add a smart cache layer, level by level, until the API is fast,
correct, and secure.

---

## The Endpoints

| Method | URL | What it does | Auth required? |
|--------|-----|--------------|----------------|
| GET | `/api/posts/` | All published posts | No |
| GET | `/api/posts/<id>/` | Single published post | No |
| POST | `/api/posts/` | Create a new post | Yes |
| GET | `/api/posts/my-drafts/` | Your own drafts only | Yes |
| GET | `/api/posts/broken-drafts/` | Buggy draft view | Yes |

---

## Level 1 — Baseline Timing

| Endpoint | First Request | Average |
|----------|--------------|---------|
| All Posts | 41.1ms | ~40ms |
| Single Post | 25.8ms | ~26ms |

---

## Level 2 — Caching the Public Data

We implemented cache-aside for `PostListView` and `PostDetailView`.

For the list endpoint, we used `"posts:list"` — a simple, static, namespaced string with no user information, since the endpoint returns the same public data to every visitor. The `posts:` prefix namespaces it clearly against other cache keys (like `posts:detail:<id>` and `my-drafts:<user_id>`) so keys don't accidentally collide across different parts of the app. The specific string doesn't matter as much as consistency — it must stay identical everywhere it's referenced (the `get()` and the `cache.delete()` in `post()`), or invalidation silently breaks.

For the single post endpoint, the key is `f"posts:detail:{post_id}"` with a 600-second TTL — longer than the list because a single published post changes far less often.

---

## Level 3 — Protecting Personal Data

For `MyDraftsView`, we scoped the cache key to `f"my-drafts:{request.user.id}"` with a 120-second TTL, ensuring each user's drafts are cached independently.

**Bug Report — `BrokenDraftsView`**

The view uses a single hardcoded cache key, `"my-drafts"`, shared by every user instead of being scoped to `request.user.id`. Whichever user's request causes the cache miss gets their draft data stored under that one shared key, and every subsequent request from any other user hits the same cache entry.

Walking through it: Alice's request causes a cache MISS on `"my-drafts"`. The view queries the database for her drafts, serializes them, and stores that data under `cache.set("my-drafts", ...)`. Alice correctly receives her own drafts. Bob's request then checks the same key and gets a cache HIT — since the key has no user-specific part, Bob is returned Alice's serialized draft data directly, without ever querying the database for his own drafts. We confirmed this by testing it directly: Bob's response was byte-for-byte identical to Alice's draft list.

Real-world impact: this is a serious data leak / privacy violation. Draft posts are meant to be private and unpublished, so any user could read another user's confidential, unreleased content simply by being the second person to call the endpoint after a cache miss. In a real product this could expose sensitive drafts or confidential documents — a serious breach of user trust.

One-line fix: replace the hardcoded key `"my-drafts"` with a user-scoped key: `f"my-drafts:{request.user.id}"` (used consistently in both the `cache.get()` and `cache.set()` calls).

---

## Level 4 — Invalidation

We added `cache.delete("posts:list")` in `PostListView.post()` right after saving a new post, so the next GET rebuilds the cache with the new data instead of serving a stale list.

`cache.delete()` simply removes the stale entry — the next request pays the cost of a cache MISS to rebuild it. Updating the cache directly with the new data would keep it "warm" so the very next GET stays fast, at the cost of extra work inside the POST request itself. We chose `cache.delete()` since it's simpler and safer to reason about, and post creation isn't the hot path here — reads are.

---

## Stretch Goal — Query-Aware Cache Key

We modified `PostListView.get()` so the cache key includes the request's query parameters:

```python
params = request.query_params.urlencode()
cache_key = f"posts:list:{params}" if params else "posts:list"
```

This means `?page=2` and no params at all get separate cache entries instead of overwriting each other, while the no-params case still matches the key used for invalidation in Level 4.

---

## Final Results

| Endpoint | Before (Level 1) | After (Level 4) | Improvement |
|----------|-----------------|-----------------|-------------|
| All Posts | 41.1ms | 3.6ms | ~91% faster |
| Single Post | 25.8ms | 1.5ms | ~94% faster |

---

## Reflection

We used a shared key for `/api/posts/` because published posts are public data — every visitor sees the exact same list. `/my-drafts/` returns private, unpublished content belonging to a single user, so it needs its own cache slot per user; using a shared key there would leak one user's private data to everyone else, exactly like the `BrokenDraftsView` bug demonstrates.

Setting `timeout=None` on the post list cache would mean the entry never expires on its own — it stays in memory indefinitely until explicitly deleted. Combined with our invalidation logic this could still work, but it's risky: any code path that changes the underlying data without calling `cache.delete()` would leave permanently stale data being served with no automatic recovery.

Caching `/my-drafts/` could still cause a bug even with the correct user-specific key if a user saves a new draft while their previous `/my-drafts/` response is still cached within the 120s TTL — there's no invalidation wired up for that write path. The user could create a new draft and immediately reload `/my-drafts/` without seeing it, since they'd still be served the stale cached list from just before the change.

---

## Key Concepts Checklist

- [x] Explain what cache-aside (lazy loading) means in your own words
- [x] Design a cache key that is shared, user-specific, or query-aware as needed
- [x] Explain why authentication must happen **before** the cache lookup
- [x] Implement cache invalidation when underlying data changes
- [x] Identify a cache key bug and explain its security impact

---

*Built for ALU BSE — Advanced Python Programming*
