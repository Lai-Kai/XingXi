"use client";

import Image from "next/image";
import { useState, type ReactNode } from "react";

export function ResearchHero({ children }: { children: ReactNode }) {
  const [imageFailed, setImageFailed] = useState(false);
  return (
    <section
      className="research-hero relative isolate overflow-hidden rounded-xl border"
      aria-labelledby="research-home-title"
    >
      {!imageFailed && (
        <Image
          src="/brand/xingxi-misty-landscape.jpg"
          alt=""
          fill
          priority
          sizes="(max-width: 768px) 100vw, 960px"
          className="object-cover object-bottom"
          onError={() => setImageFailed(true)}
        />
      )}
      <div className="research-hero-wash absolute inset-0" />
      <div className="relative px-5 py-8 sm:px-10 sm:py-10">
        <p className="text-primary mb-3 text-xs font-medium tracking-[0.25em]">
          星羲弦沚 · 吴地文史研读
        </p>
        <h1
          id="research-home-title"
          className="font-serif text-2xl leading-snug font-semibold tracking-wide sm:text-4xl"
        >
          今天想查阅哪一段木渎历史？
        </h1>
        <p className="text-muted-foreground mt-3 max-w-xl text-sm leading-6">
          从一处地名、一卷方志出发，让每一段历史都有出处。
        </p>
        {children}
      </div>
    </section>
  );
}
