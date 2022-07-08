from ..api.serializers import (CreateFollowSerializer, ShowFollowsSerializer,
                             UserSerializer)
from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404
from djoser.views import UserViewSet
from ..main.models import Follow
from ..main.paginators import SmallPageNumberPagination
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.generics import ListAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

User = get_user_model()


class CustomUserViewSet(UserViewSet):
    serializer_class = UserSerializer
    pagination_class = SmallPageNumberPagination

    @action(detail=False, methods=['get'],
            permission_classes=[IsAuthenticated])
    def me(self, request, *args, **kwargs):
        return super(CustomUserViewSet, self).me(request, *args, **kwargs)

    @action(detail=True, methods=['post'],
            permission_classes=[IsAuthenticated])
    def subscribe(self, request, id=None):
        user = request.user
        author = get_object_or_404(User, id=id)
        if user == author:
            return Response(
                {'Нельзя подписаться на самого себя!'},
                status=status.HTTP_400_BAD_REQUEST
            )
        if Follow.objects.filter(
                user=user, author=author
        ).exists():
            return Response(
                {'Нельзя подписаться повторно!'},
                status=status.HTTP_400_BAD_REQUEST
            )
        Follow.objects.create(
            user=user,
            author=author
        )
        serializer = CreateFollowSerializer(
            author,
            context={'request': request}
        )
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @subscribe.mapping.delete
    def delete_subscribe(self, request, id=None):
        author = get_object_or_404(User, id=id)
        subscription = Follow.objects.filter(
            user=request.user,
            author=author
        )
        if subscription:
            subscription.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        return Response(
            {'Попытка удалить несуществующую подписку!'},
            status=status.HTTP_400_BAD_REQUEST
        )


class FollowViewSet(ListAPIView):
    serializer_class = ShowFollowsSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = SmallPageNumberPagination

    def get_queryset(self):
        return User.objects.filter(following__user=self.request.user)
