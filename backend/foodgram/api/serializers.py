from email.headerregistry import UniqueAddressHeader
from django.shortcuts import get_object_or_404
from wsgiref.validate import validator
from rest_framework import serializers
from rest_framework.validators import UniqueTogetherValidator
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.conf import settings
from recipes.models import Tag, Recipe
from main.models import Favorite, Basket, Follow
from ingredients.models import Ingredient

User=get_user_model()

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ('username', 'email', 'id')

class FavoriteSerializer(serializers.ModelSerializer):
    user = serializers.IntegerField(source='user.id')
    recipe = serializers.IntegerField(source='recipe.id')

    class Meta:
        model = Favorite
        fields = ['user', 'recipe']

    def validate(self, data):
        user = data['user']['id']
        recipe = data['recipe']['id']
        if Favorite.objects.filter(user=user, recipe__id=recipe).exists():
            raise serializers.ValidationError(
                {
                    "errors": "Рецепт уже в избранном"
                }
            )
        return data

    def create(self, validated_data):
        user = validated_data["user"]
        recipe = validated_data["recipe"]
        Favorite.objects.get_or_create(user=user, recipe=recipe)
        return validated_data


class CreateFollowSerializer(serializers.ModelSerializer):
    user = serializers.IntegerField(source='user.id')
    author = serializers.IntegerField(source='author.id')

    class Meta:
        model = Follow
        fields = ['user', 'author']

    def validate(self, data):
        user = data['user']['id']
        author = data['author']['id']
        follow_exist = Follow.objects.filter(
            user=user, author__id=author
        ).exists()
        if user == author:
            raise serializers.ValidationError(
                {"errors": 'Вы не можете подписаться на самого себя'}
            )
        elif follow_exist:
            raise serializers.ValidationError({"errors": 'Вы уже подписаны'})
        return data

    def create(self, validated_data):
        author = validated_data.get('author')
        author = get_object_or_404(User, pk=author.get('id'))
        user = validated_data.get('user')
        return Follow.objects.create(user=user, author=author)


class RecipeFollowSerializer(serializers.ModelSerializer):
    class Meta:
        model = Recipe
        fields = ["id", "name", "image", "cooking_time"]


class ShowFollowsSerializer(UserSerializer):
    recipes = serializers.SerializerMethodField()
    recipes_count = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ('email', 'id', 'username', 'first_name',
                  'last_name', 'is_subscribed', 'recipes', 'recipes_count')

    def get_recipes(self, obj):
        recipes = obj.recipes.all()[:settings.RECIPES_LIMIT]
        return RecipeFollowSerializer(recipes, many=True).data

    def get_recipes_count(self, obj):
        queryset = Recipe.objects.filter(author=obj)
        return queryset.count()


class TagSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tag
        fields = ('id', 'name', 'color', 'slug')


class BasketSerializer(serializers.ModelSerializer):
    user = serializers.IntegerField(source='user.id')
    recipe = serializers.IntegerField(source='recipe.id')

    class Meta:
        model = Basket
        fields = '__all__'

    def validate(self, data):
        user = data['user']['id']
        recipe = data['recipe']['id']
        if Basket.objects.filter(user=user, recipe__id=recipe).exists():
            raise serializers.ValidationError(
                {
                    "errors": "рецепт уже в карзине"
                }
            )
        return data

    def create(self, validated_data):
        user = validated_data["user"]
        recipe = validated_data["recipe"]
        Basket.objects.get_or_create(user=user, recipe=recipe)
        return validated_data



class IngredientSerializer(serializers.ModelSerializer):
    name = serializers.ReadOnlyField()
    unit = serializers.ReadOnlyField()

    class Meta:
        model = Ingredient
        fields = ['id', 'name', 'unit']


class IngredientAmountSerializer(serializers.ModelSerializer):
    name = serializers.ReadOnlyField(source='ingredient.name', read_only=True)
    unit = serializers.ReadOnlyField(
        source='ingredient.unit', read_only=True
    )

    class Meta:
        model = Ingredient
        fields = ('id', 'name', 'amount', 'unit')

class IngredientAmountCreate(IngredientAmountSerializer):
    id = serializers.IntegerField(write_only=True)
    amount = serializers.IntegerField(write_only=True)

    def validate_amount(self, amount):
        if amount < 1:
            raise serializers.ValidationError(
                'Значение не может быть меньше 0.'
            )
        return amount

    def to_representation(self, instance):
        ingredient_in_recipe = [
            item for item in
            Ingredient.objects.filter(ingredient=instance)
        ]
        return IngredientAmountSerializer(ingredient_in_recipe).data



class RecipeSerializer(serializers.ModelSerializer):
    is_favorited = serializers.SerializerMethodField()
    is_in_basket = serializers.SerializerMethodField()
    tags = serializers.PrimaryKeyRelatedField(queryset=Tag.objects.all(),
                                              many=True)
    author = UserSerializer(read_only=True)
    image = serializers.ImageField()
    ingredients = IngredientAmountCreate(many=True)

    class Meta:
        model = Recipe
        fields = [
            'id', 'tags', 'author', 'ingredients', 'is_favorited',
            'get_is_in_basket', 'name', 'image', 'text',
            'cooking_time', 'pub_date'
        ]

    def get_is_favorited(self, obj):
        request = self.context.get('request')
        if request is None or request.user.is_anonymous:
            return False
        return Favorite.objects.filter(user=request.user, recipe=obj).exists()

    def get_is_in_basket(self, obj):
        request = self.context.get('request')
        if request is None or request.user.is_anonymous:
            return False
        return Basket.objects.filter(user=request.user, recipe=obj).exists()

    def create(self, validated_data):
        request = self.context.get('request')
        ingredients = validated_data.pop('ingredients')
        tags_data = validated_data.pop('tags')
        recipe = Recipe.objects.create(author=request.user, **validated_data)
        recipe.tags.set(tags_data)
        for ingredient in ingredients:
            amount = ingredient.get('amount')
            ingredient_instance = get_object_or_404(Ingredient,
                                                    pk=ingredient.get('id'))
            Ingredient.objects.create(recipe=recipe,
                                               ingredient=ingredient_instance,
                                               amount=amount)
        recipe.save()
        return recipe

    def update(self, instance, validated_data):
        ingredients_data = validated_data.pop('ingredients')
        tags_data = validated_data.pop('tags')
        recipe = Recipe.objects.filter(id=instance.id)
        recipe.update(**validated_data)
        ingredients_instance = [
            ingredient for ingredient in instance.ingredients.all()
        ]
        for item in ingredients_data:
            amount = item['amount']
            ingredient_id = item['id']
            if Ingredient.objects.filter(
                    id=ingredient_id, amount=amount
            ).exists():
                ingredients_instance.remove(
                    Ingredient.objects.get(id=ingredient_id,
                                                    amount=amount
                                                    ).ingredient)
            else:
                Ingredient.objects.get_or_create(
                    recipe=instance,
                    ingredient=get_object_or_404(Ingredient, id=ingredient_id),
                    amount=amount
                )
        if validated_data.get('image') is not None:
            instance.image = validated_data.get('image', instance.image)
        instance.ingredients.remove(*ingredients_instance)
        instance.tags.set(tags_data)
        return instance

class ReadRecipeSerializer(RecipeSerializer):
    tags = TagSerializer(read_only=True, many=True)
    author = UserSerializer(read_only=True)
    ingredients = serializers.SerializerMethodField()

    def get_ingredients(self, obj):
        ingredients = Ingredient.objects.filter(recipe=obj)
        return IngredientAmountSerializer(ingredients, many=True).data


class RecipeFollowSerializer(serializers.ModelSerializer):
    class Meta:
        model = Recipe
        fields = ["id", "name", "image", "cooking_time"]

