// [method, exact path | RegExp, body | ({ url, match, signedIn }) => body]
import { adminFixtures } from "./fixtures-admin.mjs";
import { customerFixtures } from "./fixtures-customer.mjs";
import { vendorFixtures } from "./fixtures-vendor.mjs";

export const fixtures = [...customerFixtures, ...vendorFixtures, ...adminFixtures];
