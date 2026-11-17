"use client";

import { Button } from "@vergeo/ui/src/button";
import { Select } from "@vergeo/ui/src/select";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { branchErrorKey } from "../_lib/branch-errors";
import {
  isAllowedEvidence,
  type Branch,
  type EvidenceKind,
  type ProofType,
  type createBusinessesClient,
} from "../_lib/businesses-client";

type Client = ReturnType<typeof createBusinessesClient>;

type BranchEvidenceProps = {
  client: Client;
  businessId: string;
  branch: Branch;
  onSubmitted: () => void;
};

const PROOF_TYPES: ProofType[] = ["lease", "utility_bill", "council_permit"];

/** Storefront photo + proof of premises (private Storage), then submit for review. */
export function BranchEvidence({ client, businessId, branch, onSubmitted }: BranchEvidenceProps) {
  const t = useTranslations("vendor.branches");
  const [proofType, setProofType] = useState<ProofType>("lease");
  const [done, setDone] = useState<Record<EvidenceKind, boolean>>({
    storefront_photo: false,
    premises_proof: false,
  });
  const [busy, setBusy] = useState<EvidenceKind | "submit" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const physical = branch.branch_kind === "physical";

  const upload = async (kind: EvidenceKind, file: File | undefined) => {
    if (!file) return;
    if (!isAllowedEvidence(file)) {
      setError("branches.errors.evidenceFile");
      return;
    }
    setBusy(kind);
    setError(null);
    try {
      await client.uploadEvidence(
        businessId,
        branch.id,
        kind,
        file,
        kind === "premises_proof" ? proofType : null,
      );
      setDone((prev) => ({ ...prev, [kind]: true }));
    } catch (err) {
      setError(branchErrorKey(err));
    } finally {
      setBusy(null);
    }
  };

  const submit = async () => {
    setBusy("submit");
    setError(null);
    try {
      await client.submit(businessId, branch.id);
      onSubmitted();
    } catch (err) {
      setError(branchErrorKey(err));
    } finally {
      setBusy(null);
    }
  };

  const fileInput = (kind: EvidenceKind) => (
    <label className="flex flex-col gap-1 text-sm">
      <span className="font-medium text-text">
        {t(`evidence.${kind}`)} {done[kind] ? `· ${t("evidence.uploaded")}` : ""}
      </span>
      <input
        type="file"
        accept="image/jpeg,image/png,image/webp"
        capture={kind === "storefront_photo" ? "environment" : undefined}
        disabled={busy !== null}
        onChange={(event) => void upload(kind, event.target.files?.[0])}
        className="text-sm text-text-2 file:mr-2 file:rounded file:border file:border-border file:bg-surface file:px-2 file:py-1"
      />
    </label>
  );

  return (
    <div className="space-y-3 rounded border border-border bg-bg-2 p-3">
      {physical ? (
        <>
          <p className="m-0 text-sm text-text-2">{t("evidence.help")}</p>
          {fileInput("storefront_photo")}
          <label className="flex flex-col gap-1 text-sm">
            <span className="font-medium text-text">{t("evidence.proofType")}</span>
            <Select
              value={proofType}
              onChange={(event) => setProofType(event.target.value as ProofType)}
              size="sm"
            >
              {PROOF_TYPES.map((type) => (
                <option key={type} value={type}>
                  {t(`evidence.proof.${type}`)}
                </option>
              ))}
            </Select>
          </label>
          {fileInput("premises_proof")}
        </>
      ) : (
        <p className="m-0 text-sm text-text-2">{t("evidence.onlineHelp")}</p>
      )}
      {error ? (
        <p role="alert" className="m-0 text-sm text-danger">
          {t(error.replace(/^branches\./, ""))}
        </p>
      ) : null}
      <Button
        size="sm"
        onClick={() => void submit()}
        disabled={busy !== null}
        loading={busy === "submit"}
        loadingLabel={t("actions.submitting")}
      >
        {t("actions.submit")}
      </Button>
    </div>
  );
}
