"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { homeFor, useMe } from "@/components/app-shell";
import { Spinner } from "@/components/ui";

export default function Home() {
  const me = useMe();
  const router = useRouter();
  useEffect(() => {
    if (me) router.replace(homeFor(me.role));
  }, [me, router]);
  return <Spinner />;
}
