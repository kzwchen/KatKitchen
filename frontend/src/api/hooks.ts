import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import * as api from './client'

export const keys = {
  ingredients: (q?: string) => ['ingredients', q ?? ''] as const,
  recipes: (q?: string) => ['recipes', q ?? ''] as const,
  recipe: (id: number) => ['recipe', id] as const,
  plans: () => ['plans'] as const,
  plan: (id: number) => ['plan', id] as const,
  list: (planId: number) => ['list', planId] as const,
  listById: (id: number) => ['listById', id] as const,
  history: () => ['history'] as const,
  suggestions: (listId: number) => ['suggestions', listId] as const,
  settings: () => ['settings'] as const,
}

export const useIngredients = (q?: string) =>
  useQuery({ queryKey: keys.ingredients(q), queryFn: () => api.getIngredients(q) })
export const useRecipes = (q?: string) =>
  useQuery({ queryKey: keys.recipes(q), queryFn: () => api.getRecipes(q) })
export const useRecipe = (id: number | undefined) =>
  useQuery({ queryKey: keys.recipe(id!), queryFn: () => api.getRecipe(id!), enabled: id != null })
export const usePlans = () => useQuery({ queryKey: keys.plans(), queryFn: api.getPlans })
export const usePlan = (id: number | undefined) =>
  useQuery({ queryKey: keys.plan(id!), queryFn: () => api.getPlan(id!), enabled: id != null })
export const useList = (planId: number | undefined) =>
  useQuery({
    queryKey: keys.list(planId!),
    queryFn: () => api.getList(planId!),
    enabled: planId != null,
    retry: false,
  })
export const useListHistory = () => useQuery({ queryKey: keys.history(), queryFn: api.getListHistory })
export const useListById = (id: number | undefined) =>
  useQuery({ queryKey: keys.listById(id!), queryFn: () => api.getListById(id!), enabled: id != null })
export const useSuggestions = (listId: number | undefined) =>
  useQuery({
    queryKey: keys.suggestions(listId!),
    queryFn: () => api.getSuggestions(listId!),
    enabled: listId != null,
  })
export const useSettings = () => useQuery({ queryKey: keys.settings(), queryFn: api.getSettings })

/** Wraps a mutation so it invalidates the given key prefixes on success. */
export function useInvalidatingMutation<TArgs, TResult>(
  mutationFn: (args: TArgs) => Promise<TResult>,
  invalidate: readonly (readonly unknown[])[],
) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn,
    onSuccess: () => {
      invalidate.forEach((key) => queryClient.invalidateQueries({ queryKey: key }))
    },
  })
}
