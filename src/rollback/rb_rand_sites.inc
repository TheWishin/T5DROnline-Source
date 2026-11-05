/* Reviewed paired direct TLS-generator return sites: exact whole-function or
 * instruction-block correspondence, plus both calls target the same generator.
 * Private evidence: build/eu-crossplay-2/edition-audit/.
 * Experimental mixed-program fix; keep uncommitted pending full crossplay proof. */
static constexpr RandSite kEuRandSites[] = {
    { 0x0002E34Cu, 0x0002E0E4u }, // matched function 0002E060/0002E2C8, same call
    { 0x000302D0u, 0x0002FF20u }, // paired TLS call in 51-instruction block; EU function 0002E3A0
    { 0x00030500u, 0x00030130u }, // paired TLS call in 20-instruction block; EU function 0002E3A0
    { 0x00036070u, 0x00035CA0u }, // matched function 00035C5C/0003602C, same call
    { 0x00036460u, 0x00036090u }, // matched function 00035F80/00036350, same call
    { 0x0003683Cu, 0x0003646Cu }, // matched function 00036110/000364E0, same call
    { 0x00036920u, 0x00036550u }, // matched function 00036110/000364E0, same call
    { 0x0004A33Cu, 0x00049EF4u }, // paired TLS call in 270-instruction block; EU function 00049800
    { 0x0004C5A0u, 0x0004C130u }, // paired TLS call in 81-instruction block; EU function 00049800
    { 0x00068280u, 0x00067FF8u }, // matched function 00067FB0/00068238, same call
    { 0x000683E0u, 0x00068158u }, // matched function 000680F0/00068378, same call
    { 0x00068428u, 0x000681A0u }, // matched function 000680F0/00068378, same call
    { 0x00068498u, 0x00068210u }, // matched function 000680F0/00068378, same call
    { 0x000684E0u, 0x00068258u }, // matched function 000680F0/00068378, same call
    { 0x00068588u, 0x00068300u }, // matched function 000680F0/00068378, same call
    { 0x000863F0u, 0x00085E44u }, // matched function 00085D40/000862EC, same call
    { 0x00087F78u, 0x000879A0u }, // matched function 000878CC/00087EA4, same call
    { 0x0008801Cu, 0x00087A44u }, // matched function 000878CC/00087EA4, same call
    { 0x0008813Cu, 0x00087B64u }, // matched function 000878CC/00087EA4, same call
    { 0x00088630u, 0x00088058u }, // matched function 000878CC/00087EA4, same call
    { 0x00088684u, 0x000880ACu }, // matched function 000878CC/00087EA4, same call
    { 0x000886E0u, 0x00088108u }, // matched function 000878CC/00087EA4, same call
    { 0x00088734u, 0x0008815Cu }, // matched function 000878CC/00087EA4, same call
    { 0x00088CD8u, 0x00088700u }, // matched function 000885C8/00088BA0, same call
    { 0x00088DA4u, 0x000887CCu }, // matched function 000885C8/00088BA0, same call
    { 0x00088FE8u, 0x00088A10u }, // matched function 000885C8/00088BA0, same call
    { 0x0008904Cu, 0x00088A74u }, // matched function 000885C8/00088BA0, same call
    { 0x00089108u, 0x00088B30u }, // matched function 000885C8/00088BA0, same call
    { 0x000896D8u, 0x00089100u }, // matched function 00088EE4/000894BC, same call
    { 0x00098FFCu, 0x00097AC4u }, // matched function 000978C0/00098DF8, same call
    { 0x00099274u, 0x00097D3Cu }, // matched function 00097B38/00099070, same call
    { 0x00099B50u, 0x00098618u }, // matched function 000983FC/00099934, same call
    { 0x00099DE8u, 0x000988B0u }, // matched function 000983FC/00099934, same call
    { 0x0009ABD0u, 0x00099698u }, // matched function 00098B44/0009A07C, same call
    { 0x0009AF5Cu, 0x00099A24u }, // matched function 00098B44/0009A07C, same call
    { 0x0009E6D0u, 0x0009D1A4u }, // matched function 0009CFCC/0009E4F8, same call
    { 0x0009EAA8u, 0x0009D57Cu }, // matched function 0009D3C0/0009E8EC, same call
    { 0x000A2CDCu, 0x000A17B0u }, // matched function 000A1768/000A2C94, same call
    { 0x000AA0DCu, 0x000A8BB0u }, // matched function 000A8B48/000AA074, same call
    { 0x000AA4D8u, 0x000A8FACu }, // matched function 000A8DB8/000AA2E4, same call
    { 0x000AF3ACu, 0x000ADDD0u }, // matched function 000ADD5C/000AF338, same call
    { 0x000AF5F4u, 0x000AE018u }, // matched function 000ADE74/000AF450, same call
    { 0x000AF68Cu, 0x000AE0B0u }, // matched function 000ADE74/000AF450, same call
    { 0x000AFABCu, 0x000AE4E0u }, // matched function 000AE0C8/000AF6A4, same call
    { 0x000AFC08u, 0x000AE62Cu }, // matched function 000AE0C8/000AF6A4, same call
    { 0x000B52C8u, 0x000B3CC0u }, // matched function 000B3A40/000B5048, same call
    { 0x000B5584u, 0x000B3F7Cu }, // matched function 000B3E88/000B5490, same call
    { 0x000B5640u, 0x000B4038u }, // matched function 000B3E88/000B5490, same call
    { 0x000B569Cu, 0x000B4094u }, // matched function 000B3E88/000B5490, same call
    { 0x000B56DCu, 0x000B40D4u }, // matched function 000B3E88/000B5490, same call
    { 0x000B571Cu, 0x000B4114u }, // matched function 000B3E88/000B5490, same call
    { 0x000B594Cu, 0x000B4344u }, // matched function 000B3E88/000B5490, same call
    { 0x000B5990u, 0x000B4388u }, // matched function 000B3E88/000B5490, same call
    { 0x000B59D4u, 0x000B43CCu }, // matched function 000B3E88/000B5490, same call
    { 0x000B5A4Cu, 0x000B4444u }, // matched function 000B3E88/000B5490, same call
    { 0x000B5A98u, 0x000B4490u }, // matched function 000B3E88/000B5490, same call
    { 0x000B5AE4u, 0x000B44DCu }, // matched function 000B3E88/000B5490, same call
    { 0x000B5E0Cu, 0x000B4804u }, // matched function 000B3E88/000B5490, same call
    { 0x000B62BCu, 0x000B4CB4u }, // matched function 000B3E88/000B5490, same call
    { 0x000B66FCu, 0x000B508Cu }, // paired TLS call in 372-instruction block; EU function 000B6404
    { 0x000B6828u, 0x000B51B8u }, // paired TLS call in 372-instruction block; EU function 000B6404
    { 0x000B6960u, 0x000B52F0u }, // paired TLS call in 372-instruction block; EU function 000B6404
    { 0x000B69B4u, 0x000B5344u }, // paired TLS call in 372-instruction block; EU function 000B6404
    { 0x000B6A64u, 0x000B53F4u }, // paired TLS call in 372-instruction block; EU function 000B6404
    { 0x000B6E6Cu, 0x000B57D0u }, // paired TLS call in 397-instruction block; EU function 000B6CD8
    { 0x000B6EC8u, 0x000B582Cu }, // paired TLS call in 397-instruction block; EU function 000B6CD8
    { 0x000B6F24u, 0x000B5888u }, // paired TLS call in 397-instruction block; EU function 000B6CD8
    { 0x000B6F88u, 0x000B58ECu }, // paired TLS call in 397-instruction block; EU function 000B6CD8
    { 0x000B6FDCu, 0x000B5940u }, // paired TLS call in 397-instruction block; EU function 000B6CD8
    { 0x000B702Cu, 0x000B5990u }, // paired TLS call in 397-instruction block; EU function 000B6CD8
    { 0x000B729Cu, 0x000B5C00u }, // paired TLS call in 397-instruction block; EU function 000B6CD8
    { 0x000B7C0Cu, 0x000B63C8u }, // paired TLS call in 28-instruction block; EU function 000B79DC
    { 0x000B8890u, 0x000B7058u }, // matched function 000B6B4C/000B8384, same call
    { 0x000B88E4u, 0x000B70ACu }, // matched function 000B6B4C/000B8384, same call
    { 0x000B8938u, 0x000B7100u }, // matched function 000B6B4C/000B8384, same call
    { 0x000B8B30u, 0x000B72F8u }, // matched function 000B6B4C/000B8384, same call
    { 0x000B8B80u, 0x000B7348u }, // matched function 000B6B4C/000B8384, same call
    { 0x000B8BD8u, 0x000B73A0u }, // matched function 000B6B4C/000B8384, same call
    { 0x000B8F54u, 0x000B771Cu }, // matched function 000B6B4C/000B8384, same call
    { 0x000B919Cu, 0x000B7964u }, // matched function 000B6B4C/000B8384, same call
    { 0x000B922Cu, 0x000B79F4u }, // matched function 000B6B4C/000B8384, same call
    { 0x000B927Cu, 0x000B7A44u }, // matched function 000B6B4C/000B8384, same call
    { 0x000B9418u, 0x000B7BE0u }, // matched function 000B6B4C/000B8384, same call
    { 0x000B9460u, 0x000B7C28u }, // matched function 000B6B4C/000B8384, same call
    { 0x000B94A8u, 0x000B7C70u }, // matched function 000B6B4C/000B8384, same call
    { 0x000B990Cu, 0x000B80D4u }, // matched function 000B6B4C/000B8384, same call
    { 0x000B99D8u, 0x000B81A0u }, // matched function 000B6B4C/000B8384, same call
    { 0x000BC36Cu, 0x000BAB34u }, // matched function 000BA0B4/000BB8EC, same call
    { 0x000BC400u, 0x000BABC8u }, // matched function 000BA0B4/000BB8EC, same call
    { 0x000BF014u, 0x000BD7DCu }, // matched function 000BD6A8/000BEEE0, same call
    { 0x000BF1E0u, 0x000BD9A8u }, // matched function 000BD928/000BF160, same call
    { 0x000BF638u, 0x000BDE00u }, // matched function 000BDCC4/000BF4FC, same call
    { 0x000CD1B8u, 0x000CB934u }, // matched function 000CB840/000CD0C4, same call
    { 0x000CD260u, 0x000CB9DCu }, // matched function 000CB9A0/000CD224, same call
    { 0x000EA108u, 0x000E87F4u }, // matched function 000E87DC/000EA0F0, same call
    { 0x000EA1ECu, 0x000E88D8u }, // matched function 000E88BC/000EA1D0, same call
    { 0x000EA318u, 0x000E8A04u }, // matched function 000E89E8/000EA2FC, same call
    { 0x000EC6DCu, 0x000EADC8u }, // matched function 000EAD80/000EC694, same call
    { 0x001006D4u, 0x000FEDC0u }, // 151-word identical function US000FED98/EU001006AC; lifter split differs
    { 0x00100738u, 0x000FEE24u }, // 151-word identical function US000FED98/EU001006AC; lifter split differs
    { 0x0010079Cu, 0x000FEE88u }, // 151-word identical function US000FED98/EU001006AC; lifter split differs
    { 0x00100804u, 0x000FEEF0u }, // 151-word identical function US000FED98/EU001006AC; lifter split differs
    { 0x00100838u, 0x000FEF24u }, // 151-word identical function US000FED98/EU001006AC; lifter split differs
    { 0x0010089Cu, 0x000FEF88u }, // 151-word identical function US000FED98/EU001006AC; lifter split differs
    { 0x001008D4u, 0x000FEFC0u }, // 151-word identical function US000FED98/EU001006AC; lifter split differs
    { 0x00123710u, 0x00121E28u }, // matched function 00121E0C/001236F4, same call
    { 0x00140988u, 0x0013EEECu }, // paired TLS call in 105-instruction block; EU function 0014091C
    { 0x00218450u, 0x00214F68u }, // matched function 00214F5C/00218444, same call
    { 0x00218B5Cu, 0x00215674u }, // matched function 002155D8/00218AC0, same call
    { 0x00223650u, 0x00220168u }, // matched function 0022015C/00223644, same call
    { 0x0026365Cu, 0x0025FFD4u }, // matched function 0025FEA0/00263528, same call
    { 0x0026368Cu, 0x00260004u }, // matched function 0025FEA0/00263528, same call
    { 0x002636D0u, 0x00260048u }, // matched function 0025FEA0/00263528, same call
    { 0x0028E240u, 0x0028A990u }, // matched function 0028A938/0028E1E8, same call
    { 0x0029709Cu, 0x002937B4u }, // matched function 00293698/00296F80, same call
    { 0x002972D8u, 0x002939F0u }, // matched function 00293698/00296F80, same call
    { 0x002974ACu, 0x00293BC4u }, // matched function 00293698/00296F80, same call
    { 0x002974F4u, 0x00293C0Cu }, // matched function 00293698/00296F80, same call
    { 0x0029752Cu, 0x00293C44u }, // matched function 00293698/00296F80, same call
    { 0x00297564u, 0x00293C7Cu }, // matched function 00293698/00296F80, same call
    { 0x002975D8u, 0x00293CF0u }, // matched function 00293698/00296F80, same call
    { 0x002A548Cu, 0x002A1BA4u }, // matched function 002A1B28/002A5410, same call
    { 0x002A55BCu, 0x002A1CD4u }, // matched function 002A1B28/002A5410, same call
    { 0x002A6530u, 0x002A2C48u }, // matched function 002A2AAC/002A6394, same call
    { 0x002A8844u, 0x002A4F5Cu }, // matched function 002A4E50/002A8738, same call
    { 0x002A9044u, 0x002A575Cu }, // matched function 002A5470/002A8D58, same call
    { 0x002A95B0u, 0x002A5CC8u }, // matched function 002A5B3C/002A9424, same call
    { 0x002ABA88u, 0x002A7548u }, // matched function 002A74D4/002ABA14, same call
    { 0x002FCE74u, 0x002F8934u }, // matched function 002F88B8/002FCDF8, same call
    { 0x00322484u, 0x0031DF44u }, // matched function 0031DF28/00322468, same call
};
