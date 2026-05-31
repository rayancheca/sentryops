// Display labels and semantic-tone mappings for asset enums. Centralized so the
// list page, detail page, and dependency graph render the same vocabulary.

import type { BadgeProps } from "@/components/ui";
import type { AssetType, Environment, LifecycleState } from "@/lib/types";

export const ASSET_TYPE_LABEL: Record<AssetType, string> = {
  host: "Host",
  network_device: "Network",
  service: "Service",
  software_license: "License",
  cloud_resource: "Cloud",
};

export const ENVIRONMENT_LABEL: Record<Environment, string> = {
  prod: "PROD",
  staging: "STAGING",
  dev: "DEV",
};

// prod is load-bearing — flag it with the accent/danger weight; lower envs stay calm.
export const ENVIRONMENT_VARIANT: Record<Environment, NonNullable<BadgeProps["variant"]>> = {
  prod: "info",
  staging: "warn",
  dev: "outline",
};

export const LIFECYCLE_LABEL: Record<LifecycleState, string> = {
  provisioning: "Provisioning",
  active: "Active",
  maintenance: "Maintenance",
  retired: "Retired",
  disposed: "Disposed",
};

// Lifecycle tone: active=ok, maintenance=warn, retired/disposed muted, provisioning info.
export const LIFECYCLE_VARIANT: Record<LifecycleState, NonNullable<BadgeProps["variant"]>> = {
  provisioning: "info",
  active: "ok",
  maintenance: "warn",
  retired: "outline",
  disposed: "default",
};

export const ASSET_TYPE_OPTIONS: ReadonlyArray<{ value: AssetType; label: string }> = (
  Object.keys(ASSET_TYPE_LABEL) as AssetType[]
).map((value) => ({ value, label: ASSET_TYPE_LABEL[value] }));

export const ENVIRONMENT_OPTIONS: ReadonlyArray<{ value: Environment; label: string }> = (
  Object.keys(ENVIRONMENT_LABEL) as Environment[]
).map((value) => ({ value, label: ENVIRONMENT_LABEL[value] }));

export const LIFECYCLE_OPTIONS: ReadonlyArray<{ value: LifecycleState; label: string }> = (
  Object.keys(LIFECYCLE_LABEL) as LifecycleState[]
).map((value) => ({ value, label: LIFECYCLE_LABEL[value] }));
