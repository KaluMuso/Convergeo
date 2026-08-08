import { createTranslator, type AbstractIntlMessages } from "next-intl";
import { getMessages } from "next-intl/server";

import { TopUtilityBar } from "../(shop)/_components/top-utility-bar";

type TopUtilityBarSlotProps = {
  locale: string;
};

/** Server wrapper — loads common.* labels for the dark utility strip. */
export async function TopUtilityBarSlot({ locale }: TopUtilityBarSlotProps) {
  const messages = (await getMessages()) as AbstractIntlMessages;
  const tCommon = createTranslator({ locale, messages, namespace: "common" });
  const contactEmail = tCommon("contact.email");
  const contactPhone = tCommon("contact.phone");

  return (
    <TopUtilityBar
      locale={locale}
      labels={{
        ariaLabel: tCommon("utilityBar.ariaLabel"),
        localeAria: tCommon("locale.switchAria"),
        localeNames: {
          en: tCommon("locale.names.en"),
          bem: tCommon("locale.names.bem"),
          nya: tCommon("locale.names.nya"),
          fr: tCommon("locale.names.fr"),
        },
        phone: contactPhone,
        email: contactEmail,
        socialAria: tCommon("utilityBar.socialAria"),
        facebookAria: tCommon("utilityBar.facebookAria"),
        twitterAria: tCommon("utilityBar.twitterAria"),
        instagramAria: tCommon("utilityBar.instagramAria"),
        emailAria: tCommon("utilityBar.emailAria"),
      }}
      links={{
        phoneHref: `tel:${contactPhone.replace(/\s+/g, "")}`,
        emailHref: `mailto:${contactEmail}`,
        facebook: tCommon("social.facebook"),
        twitter: tCommon("social.twitter"),
        instagram: tCommon("social.instagram"),
      }}
    />
  );
}
