import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiFetch } from '../../api/p4Fetch';

export function useApiQuery<T>(key: string[], path: string) {
  return useQuery<T>({ queryKey: key, queryFn: () => apiFetch<T>(path) });
}

export function useApiMutation<T, B = unknown>(key: string[], path: string, method: string = 'POST') {
  const queryClient = useQueryClient();
  return useMutation<T, Error, B>({
    mutationFn: (body) => apiFetch<T>(path, { method, body: JSON.stringify(body) }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: key }),
  });
}
