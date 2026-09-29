# Owner action proof boundary

`Ed25519OwnerActionVerifier` implements the trusted-verifier interfaces already used for personal-state activation and claim quarantine. The product must supply a previously enrolled host-bound public key and a durable mapping from exact Experience event IDs to signatures. The proof cannot supply its own trusted key.

The signed message includes a versioned domain, the action type, product/host/encryption scope, and the exact Experience event digest. The surrounding activation/quarantine path separately compares the event's encrypted request payload to the expected candidate or Claim head. A valid signature authorizes that exact action only after the product's owner policy allows it.

Tests use newly generated synthetic keys. The selected-backend gate signs an actual deletion-request Experience event before applying quarantine. This verifies cryptographic binding, not production enrollment, device authentication, key custody, lost-key recovery, consent UX, or authorization of a real person.
