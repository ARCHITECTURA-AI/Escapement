"use client";

import useSWR from "swr";
import { fetcher } from "./api";
import type { Me, Meta } from "./types";

export function useMe() {
  const { data, error, isLoading, mutate } = useSWR<Me>("/api/v1/me", fetcher, { revalidateOnFocus: true });
  return { me: data, user: data?.user ?? null, error, isLoading, mutate };
}

export function useMeta() {
  const { data } = useSWR<Meta>("/api/v1/meta", fetcher, { revalidateOnFocus: false });
  return data;
}

export function useApi<T>(path: string | null, refreshInterval?: number) {
  return useSWR<T>(path, fetcher, { refreshInterval, revalidateOnFocus: false, shouldRetryOnError: false });
}
