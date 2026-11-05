/* Exact reviewed EU round-controller immediates; US counterparts are proven
 * by paired instruction blocks. Private proof: edition-audit/postko-all-small-immediates.json. */
static constexpr Site kSites[] = {
    { 0x00042464u, 0x2F80006Eu, 0x2F800082u },
    { 0x000425E4u, 0x2F800162u, 0x2F800176u },
    { 0x00042AC4u, 0x38000064u, 0x38000078u },
    { 0x000439CCu, 0x2F800063u, 0x2F800077u },
    { 0x00043B94u, 0x2F80005Au, 0x2F80006Eu },
    { 0x00043F48u, 0x2F8B0018u, 0x2F8B001Du },
    { 0x00043F60u, 0x2F800018u, 0x2F80001Du },
    { 0x00044238u, 0x2F80006Eu, 0x2F800082u },
    { 0x00044CF0u, 0x2B8005DCu, 0x2B800708u },
};
