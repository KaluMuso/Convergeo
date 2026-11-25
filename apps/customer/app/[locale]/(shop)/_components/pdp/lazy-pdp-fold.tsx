"use client";

import dynamic from "next/dynamic";

import type { AboutThisItemProps } from "./about-this-item";
import type { PdpSectionNavProps } from "./section-nav";
import type { PdpSpecTableProps } from "./spec-table";

const PdpSectionNav = dynamic(() => import("./section-nav").then((m) => m.PdpSectionNav), {
  ssr: true,
});

const AboutThisItem = dynamic(() => import("./about-this-item").then((m) => m.AboutThisItem), {
  ssr: true,
});

const PdpSpecTable = dynamic(() => import("./spec-table").then((m) => m.PdpSpecTable), {
  ssr: true,
});

export function LazyPdpSectionNav(props: PdpSectionNavProps) {
  return <PdpSectionNav {...props} />;
}

export function LazyAboutThisItem(props: AboutThisItemProps) {
  return <AboutThisItem {...props} />;
}

export function LazyPdpSpecTable(props: PdpSpecTableProps) {
  return <PdpSpecTable {...props} />;
}
