"use client";

import {
  BUSINESS_ARCHETYPES,
  BUSINESS_CATEGORIES,
  type BusinessArchetype,
  type BusinessCategory,
} from "../_lib/types";
import { Button, FormField, Input, Select } from "../_lib/ui";

import type { ChangeEvent, FormEvent } from "react";

type BusinessBasicsStepProps = {
  businessName: string;
  businessCategory: string;
  businessArchetype: string;
  onBusinessNameChange: (value: string) => void;
  onBusinessCategoryChange: (value: string) => void;
  onBusinessArchetypeChange: (value: string) => void;
  onContinue: () => void;
  labels: {
    heading: string;
    intro: string;
    nameLabel: string;
    namePlaceholder: string;
    categoryLabel: string;
    categoryPlaceholder: string;
    categories: Record<BusinessCategory, string>;
    archetypeLabel: string;
    archetypePlaceholder: string;
    archetypes: Record<BusinessArchetype, string>;
    continue: string;
    saving: string;
    required: string;
  };
  saving?: boolean;
};

export function BusinessBasicsStep({
  businessName,
  businessCategory,
  businessArchetype,
  onBusinessNameChange,
  onBusinessCategoryChange,
  onBusinessArchetypeChange,
  onContinue,
  labels,
  saving = false,
}: BusinessBasicsStepProps) {
  const nameError = !businessName.trim() ? labels.required : undefined;
  const categoryError = !businessCategory.trim() ? labels.required : undefined;
  const archetypeError = !businessArchetype.trim()
    ? labels.required
    : undefined;

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault();
    if (nameError || categoryError || archetypeError) {
      return;
    }
    onContinue();
  };

  return (
    <form className="flex flex-col gap-4" onSubmit={handleSubmit}>
      <header className="space-y-1">
        <h1 className="font-display text-h3 text-display-ink">
          {labels.heading}
        </h1>
        <p className="text-sm text-text-2">{labels.intro}</p>
      </header>

      <FormField
        label={labels.nameLabel}
        required
        requiredMarker="*"
        errorMessage={nameError}
      >
        <Input
          value={businessName}
          onChange={(event: ChangeEvent<HTMLInputElement>) =>
            onBusinessNameChange(event.target.value)
          }
          placeholder={labels.namePlaceholder}
          autoComplete="organization"
          error={Boolean(nameError)}
        />
      </FormField>

      <FormField
        label={labels.archetypeLabel}
        required
        requiredMarker="*"
        errorMessage={archetypeError}
      >
        <Select
          value={businessArchetype}
          onChange={(event: ChangeEvent<HTMLSelectElement>) =>
            onBusinessArchetypeChange(event.target.value)
          }
          error={Boolean(archetypeError)}
        >
          <option value="">{labels.archetypePlaceholder}</option>
          {BUSINESS_ARCHETYPES.map((key) => (
            <option key={key} value={key}>
              {labels.archetypes[key]}
            </option>
          ))}
        </Select>
      </FormField>

      <FormField
        label={labels.categoryLabel}
        required
        requiredMarker="*"
        errorMessage={categoryError}
      >
        <Select
          value={businessCategory}
          onChange={(event: ChangeEvent<HTMLSelectElement>) =>
            onBusinessCategoryChange(event.target.value)
          }
          error={Boolean(categoryError)}
        >
          <option value="">{labels.categoryPlaceholder}</option>
          {BUSINESS_CATEGORIES.map((key) => (
            <option key={key} value={key}>
              {labels.categories[key]}
            </option>
          ))}
        </Select>
      </FormField>

      <Button
        type="submit"
        className="w-full"
        loading={saving}
        loadingLabel={labels.saving}
        disabled={Boolean(nameError || categoryError || archetypeError)}
      >
        {labels.continue}
      </Button>
    </form>
  );
}
