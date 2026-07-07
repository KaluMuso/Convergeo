/* eslint-disable @vergeo/no-hardcoded-strings -- dev-only UI preview; gated off in production */
"use client";

import { Button } from "@vergeo/ui/src/button";
import { Checkbox } from "@vergeo/ui/src/checkbox";
import { FormField } from "@vergeo/ui/src/form-field";
import { Input } from "@vergeo/ui/src/input";
import { OtpField } from "@vergeo/ui/src/otp-field";
import { Radio } from "@vergeo/ui/src/radio";
import { Select } from "@vergeo/ui/src/select";
import { Switch } from "@vergeo/ui/src/switch";
import { Textarea } from "@vergeo/ui/src/textarea";
import { useId, useState } from "react";

function SectionBlock({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-3 rounded-lg border border-border bg-surface p-4">
      <h3 className="font-display text-lg text-display-ink">{title}</h3>
      {children}
    </div>
  );
}

export function FormsSection() {
  const checkboxId = useId();
  const radioAId = useId();
  const radioBId = useId();
  const switchId = useId();
  const [otp, setOtp] = useState("");

  return (
    <section id="forms" className="scroll-mt-4 flex flex-col gap-6">
      <h2 className="font-display text-2xl text-display-ink">Form controls</h2>

      <SectionBlock title="Button — variants">
        <div className="flex flex-wrap gap-2">
          <Button loadingLabel="Loading">Primary</Button>
          <Button variant="secondary" loadingLabel="Loading">
            Secondary
          </Button>
          <Button variant="ghost" loadingLabel="Loading">
            Ghost
          </Button>
          <Button variant="destructive" loadingLabel="Loading">
            Destructive
          </Button>
        </div>
      </SectionBlock>

      <SectionBlock title="Button — sizes & states">
        <div className="flex flex-wrap items-center gap-2">
          <Button size="sm" loadingLabel="Loading">
            Small
          </Button>
          <Button size="md" loadingLabel="Loading">
            Medium
          </Button>
          <Button size="lg" loadingLabel="Loading">
            Large
          </Button>
          <Button loading loadingLabel="Please wait">
            Loading
          </Button>
          <Button disabled loadingLabel="Loading">
            Disabled
          </Button>
        </div>
      </SectionBlock>

      <SectionBlock title="Input">
        <div className="flex max-w-md flex-col gap-3">
          <Input placeholder="Default input" aria-label="Default input" />
          <Input size="sm" placeholder="Small" aria-label="Small input" />
          <Input size="lg" placeholder="Large" aria-label="Large input" />
          <Input error placeholder="Error state" aria-label="Error input" />
          <Input disabled placeholder="Disabled" aria-label="Disabled input" />
        </div>
      </SectionBlock>

      <SectionBlock title="Select">
        <Select className="max-w-md" aria-label="Category">
          <option value="">Choose category</option>
          <option value="beauty">Beauty</option>
          <option value="food">Food</option>
        </Select>
        <Select className="max-w-md" error aria-label="Error select">
          <option value="">Error select</option>
        </Select>
        <Select className="max-w-md" disabled aria-label="Disabled select">
          <option value="">Disabled</option>
        </Select>
      </SectionBlock>

      <SectionBlock title="Textarea">
        <Textarea className="max-w-md" placeholder="Message" aria-label="Message" />
        <Textarea className="max-w-md" error placeholder="Error" aria-label="Error textarea" />
        <Textarea
          className="max-w-md"
          disabled
          placeholder="Disabled"
          aria-label="Disabled textarea"
        />
      </SectionBlock>

      <SectionBlock title="OTP field">
        <OtpField
          value={otp}
          onChange={setOtp}
          ariaLabel="One-time passcode"
          getDigitAriaLabel={(index) => `Digit ${index + 1}`}
        />
      </SectionBlock>

      <SectionBlock title="Checkbox, radio, switch">
        <Checkbox id={checkboxId} label="Accept terms" defaultChecked />
        <Checkbox id={`${checkboxId}-off`} label="Disabled" disabled />
        <div className="flex flex-col gap-2">
          <Radio id={radioAId} name="preview-radio" label="Option A" defaultChecked />
          <Radio id={radioBId} name="preview-radio" label="Option B" />
          <Radio
            id={`${radioBId}-disabled`}
            name="preview-radio-disabled"
            label="Disabled"
            disabled
          />
        </div>
        <Switch id={switchId} label="Notifications" defaultChecked />
        <Switch id={`${switchId}-off`} label="Disabled switch" disabled />
      </SectionBlock>

      <SectionBlock title="Form field wrapper">
        <FormField label="Email" helpText="We never share your email." required requiredMarker="*">
          <Input type="email" placeholder="you@example.com" />
        </FormField>
        <FormField label="Phone" errorMessage="Enter a valid Zambian number.">
          <Input error placeholder="+260 …" />
        </FormField>
      </SectionBlock>
    </section>
  );
}
