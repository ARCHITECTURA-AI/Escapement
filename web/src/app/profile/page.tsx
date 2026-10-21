"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { Page, Spinner } from "@/components/ui";
import { useMe } from "@/lib/hooks";

export default function MyProfile() {
  const { user, isLoading } = useMe();
  const router = useRouter();
  useEffect(() => {
    if (isLoading) return;
    router.replace(user ? `/u/${user.handle}` : "/signin?next=/profile");
  }, [user, isLoading, router]);
  return <Page><Spinner label="Opening your profile" /></Page>;
}
