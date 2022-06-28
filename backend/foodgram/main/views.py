from django.shortcuts import render, get_object_or_404, redirect
from django.core.paginator import Paginator
from django.core.cache import cache
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework import viewsets, status, permissions
from recipes.models import Recipe
from ingredients.models import Ingredient
from recipes.forms import RecipeForm
from recipes.models import Tag
from .models import Follow, Favorite, Basket
from .ingredients_count import ing_count
from .filters import RecipeFilter, IngredientFilter
from api.permissions import AuthorAdminOrReadOnly
from api.serializers import RecipeSerializer, ReadRecipeSerializer, FavoriteSerializer, BasketSerializer, IngredientSerializer, RecipeFollowSerializer, TagSerializer
from .paginators import CustomPageNumberPagination


User=get_user_model()

@api_view(['GET', ])
@permission_classes([permissions.IsAuthenticated])
def download_basket(request):
    user = request.user
    basket = user.buyer.all()
    txt_file_output = ing_count(basket)
    response = HttpResponse(txt_file_output, 'Content-Type: text/plain')
    response['Content-Disposition'] = (
        'attachment;' 'filename="Список_покупок.txt"'
    )
    return response

class RecipeViewSet(viewsets.ModelViewSet):
    queryset = Recipe.objects.all().order_by('-id')
    permission_classes = [AuthorAdminOrReadOnly]
    filter_backends = [DjangoFilterBackend]
    filterset_class = RecipeFilter
    pagination_class = CustomPageNumberPagination

    def get_serializer_class(self):
        if self.request.method == 'GET':
            return ReadRecipeSerializer
        return RecipeSerializer

    @action(detail=True, permission_classes=[AuthorAdminOrReadOnly])
    def favorite(self, request, pk):
        data = {'user': request.user.id, 'recipe': pk}
        serializer = FavoriteSerializer(
            data=data,
            context={'request': request},
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @favorite.mapping.delete
    def delete_favorite(self, request, pk):
        if request.user.is_anonymous:
            return Response(status=status.HTTP_401_UNAUTHORIZED)
        recipe = get_object_or_404(Recipe, id=pk)
        try:
            Favorite.objects.get(user=request.user, recipe=recipe).delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        except Favorite.DoesNotExist:
            return Response(
                'Рецепт уже отсутствует в избранном.',
                status=status.HTTP_400_BAD_REQUEST,
            )

    @action(detail=True, permission_classes=[AuthorAdminOrReadOnly])
    def basket(self, request, pk):
        data = {'user': request.user.id, 'recipe': pk}
        serializer = BasketSerializer(
            data=data,
            context={'request': request},
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @basket.mapping.delete
    def delete_basket(self, request, pk):
        if request.user.is_anonymous:
            return Response(status=status.HTTP_401_UNAUTHORIZED)
        bad_request = Response(
            'Рецепт уже отсутствует в списке покупок.',
            status=status.HTTP_400_BAD_REQUEST,
        )
        try:
            try:
                recipe = Recipe.objects.get(id=pk)
            except Recipe.DoesNotExist:
                return bad_request
            shopping_list = Basket.objects.get(
                user=request.user,
                recipe=recipe,
            )
            shopping_list.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        except Basket.DoesNotExist:
            return bad_request

    @action(detail=False, permission_classes=[permissions.IsAuthenticated])
    def download_basket(self, request):
        ingredients_list = Basket.objects.filter(
            recipe__buyer__user=request.user
        )
        list_to_buy = ing_count(ingredients_list)
        return download_response(list_to_buy, 'Список_покупок.txt')


class TagsViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = TagSerializer
    queryset = Tag.objects.all()
    permission_classes = (permissions.AllowAny,)
    pagination_class = None


class IngredientViewSet(viewsets.ModelViewSet):
    serializer_class = IngredientSerializer
    queryset = Ingredient.objects.all()
    permission_classes = (permissions.AllowAny, )
    pagination_class = None
    filterset_class = IngredientFilter


class BasketView(APIView):
    permission_classes = (permissions.IsAuthenticated,)
    http_method_names = ['get', 'delete']

    def get(self, request, recipe_id):
        user = request.user
        recipe = get_object_or_404(Recipe, id=recipe_id)
        serializer = BasketSerializer(
            data={'user': user.id, 'recipe': recipe.id},
            context={'request': request}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save(recipe=recipe, user=request.user)
        serializer = RecipeFollowSerializer(recipe)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def delete(self, request, recipe_id):
        user = request.user
        basket = get_object_or_404(Basket, user=user, recipe__id=recipe_id)
        basket.delete()
        return Response(
            f'Рецепт {basket.recipe} удален из корзины у пользователя {user}, '
            f'status=status.HTTP_204_NO_CONTENT'
        )