# blog/views.py
#
# =============================================================================
#  SMART CACHE LAYER — GUIDED ACTIVITY
#  Advanced Python Programming | ALU BSE
# =============================================================================
#
#  This file contains three API views. Your job is to add caching to each one.
#  Read each TODO carefully — they build on each other.
#
#  Run the timing script first (docs/ACTIVITY.md → Level 1) to see
#  how slow the uncached responses are before you begin.
# =============================================================================

import time
import logging

from django.core.cache import cache
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework import status

from .models import Post
from .serializers import PostSerializer

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# LEVEL 2 — Shared Cache (Public Data)
# ---------------------------------------------------------------------------

class PostListView(APIView):
    """
    GET  /api/posts/       — Returns all published posts.
    POST /api/posts/       — Creates a new post (authenticated users only).
    """

    def get_permissions(self):
        if self.request.method == "POST":
            return [IsAuthenticated()]
        return [AllowAny()]

    def get(self, request):
        # ---------------------------------------------------------------
        # LEVEL 2 + STRETCH GOAL: cache-aside for the public post list,
        # with a query-aware cache key so different filters/pages don't
        # overwrite each other's cached entry (e.g. ?status=published vs
        # ?status=published&page=2 get separate cache slots).
        # Base key stays "posts:list" when there are no query params at
        # all, so the Level 4 invalidation below still targets the
        # right entry for the common no-params case.
        # ---------------------------------------------------------------
        params = request.query_params.urlencode()
        cache_key = f"posts:list:{params}" if params else "posts:list"
        data = cache.get(cache_key)

        if data is None:
            posts = Post.objects.filter(status=Post.STATUS_PUBLISHED).select_related("author")
            serializer = PostSerializer(posts, many=True)
            data = serializer.data
            cache.set(cache_key, data, timeout=300)

        return Response(data)

    def post(self, request):
        # ---------------------------------------------------------------
        # LEVEL 4: invalidate the list cache after creating a new post,
        # so the next GET reflects the new data instead of a stale list.
        # Key must match exactly the key used in get() above: "posts:list"
        # ---------------------------------------------------------------

        serializer = PostSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(author=request.user)
            cache.delete("posts:list")
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# ---------------------------------------------------------------------------
# LEVEL 2 (continued) — Single Post Cache
# ---------------------------------------------------------------------------

class PostDetailView(APIView):
    """
    GET /api/posts/<post_id>/ — Returns a single published post.
    """

    permission_classes = [AllowAny]

    def get(self, request, post_id: int):
        # ---------------------------------------------------------------
        # LEVEL 2 (continued): cache-aside for a single post.
        # Key includes post_id so different posts never collide.
        # Longer TTL (600s) is fine here since a single published post
        # changes far less often than the whole list.
        # ---------------------------------------------------------------
        cache_key = f"posts:detail:{post_id}"
        data = cache.get(cache_key)

        if data is None:
            try:
                post = Post.objects.select_related("author").get(
                    id=post_id, status=Post.STATUS_PUBLISHED
                )
            except Post.DoesNotExist:
                return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

            serializer = PostSerializer(post)
            data = serializer.data
            cache.set(cache_key, data, timeout=600)

        return Response(data)


# ---------------------------------------------------------------------------
# LEVEL 3 — User-Isolated Cache (Personal Data)
# ---------------------------------------------------------------------------

class MyDraftsView(APIView):
    """
    GET /api/posts/my-drafts/ — Returns draft posts for the logged-in user only.

    !! SECURITY CRITICAL !!
    This endpoint returns private data. Every student must ensure
    that User A can never see User B's drafts under any circumstances.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        # ---------------------------------------------------------------
        # LEVEL 3: user-isolated cache-aside for private draft data.
        #
        # SECURITY: the cache key MUST include request.user.id.
        # If we used a shared key like "my-drafts" for every user, whoever
        # hits this endpoint first would have their drafts cached under
        # that one shared key. Every other user who then requests this
        # endpoint would get a cache HIT on that same key and be served
        # the first user's private, unpublished drafts instead of their
        # own — e.g. if we used a shared key, Alice's drafts would be
        # returned to Bob. That's a serious data leak, so the TTL is also
        # kept short (120s) since personal data should expire quickly.
        # ---------------------------------------------------------------
        cache_key = f"my-drafts:{request.user.id}"
        data = cache.get(cache_key)

        if data is None:
            drafts = Post.objects.filter(
                author=request.user,
                status=Post.STATUS_DRAFT
            ).select_related("author")

            serializer = PostSerializer(drafts, many=True)
            data = serializer.data
            cache.set(cache_key, data, timeout=120)

        return Response(data)


# ---------------------------------------------------------------------------
# BONUS — Deliberately Broken View (Level 3 Bug-Spotting)
# ---------------------------------------------------------------------------

class BrokenDraftsView(APIView):
    """
    GET /api/posts/broken-drafts/

    This view has a critical security bug.
    Your task: read the code, find the bug, and explain it in the activity sheet.
    DO NOT fix the code here — write your answer in docs/ACTIVITY.md.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        # !! BUG: find it, name it, explain the real-world impact !!
        data = cache.get("my-drafts")
        if data is None:
            drafts = Post.objects.filter(
                author=request.user,
                status=Post.STATUS_DRAFT
            ).select_related("author")
            serializer = PostSerializer(drafts, many=True)
            data = serializer.data
            cache.set("my-drafts", data, timeout=120)
        return Response(data)
