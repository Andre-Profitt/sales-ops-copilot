/*
 * Custom frida-trace handler for BCryptCreateHash.
 *
 * Captures the algorithm handle + HMAC key (if BCRYPT_ALG_HANDLE_HMAC_FLAG set).
 * Critical for decoding think-cell's HMAC scheme: the secret key passed here
 * is what we need to identify (token's `hash` field? license key derivative?).
 *
 * Signature:
 *   NTSTATUS BCryptCreateHash(
 *     [in, out] BCRYPT_ALG_HANDLE  hAlgorithm,    // args[0]
 *     [out]     BCRYPT_HASH_HANDLE *phHash,       // args[1] (out ptr)
 *     [in, out, opt] PUCHAR        pbHashObject,  // args[2]
 *     [in, opt] ULONG              cbHashObject,  // args[3]
 *     [in, opt] PUCHAR             pbSecret,      // args[4] = HMAC key
 *     [in, opt] ULONG              cbSecret,      // args[5] = HMAC key length
 *     [in]      ULONG              dwFlags        // args[6]
 *   );
 *
 * BCRYPT_ALG_HANDLE_HMAC_FLAG = 0x00000008
 */
{
  onEnter(log, args, state) {
    const hAlg = args[0].toString();
    const cbSecret = args[5].toInt32();
    const flags = args[6].toInt32();
    const isHmac = (flags & 0x08) !== 0;
    let secretHex = '';
    if (cbSecret > 0 && cbSecret < 4096) {
      try {
        const buf = new Uint8Array(args[4].readByteArray(cbSecret));
        let h = '';
        for (let i = 0; i < buf.length; i++) {
          h += buf[i].toString(16).padStart(2, '0');
        }
        secretHex = h;
      } catch (e) {
        secretHex = '<readByteArray failed: ' + e.message + '>';
      }
    } else if (cbSecret >= 4096) {
      secretHex = '<too large: ' + cbSecret + ' bytes>';
    } else {
      secretHex = '<no secret / cbSecret=0 — plain hash, not HMAC>';
    }
    state.hAlg = hAlg;
    state.flagsHex = '0x' + flags.toString(16);
    state.isHmac = isHmac;
    log('BCryptCreateHash hAlg=' + hAlg +
        ' flags=' + state.flagsHex +
        ' isHmac=' + isHmac +
        ' cbSecret=' + cbSecret +
        ' secret_hex=' + secretHex);
  },
  onLeave(log, retval, state) {
    log('BCryptCreateHash ret=' + retval.toInt32());
  }
}
