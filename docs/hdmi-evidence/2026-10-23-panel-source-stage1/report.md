## locked: firmware log against stock 10-07

```
reference: 297 records, ticks 287978..290230
ours:      237 records, ticks 307..22864

milestone                   reference       ours
SetSource(3)                   287978        307
AppTopSetSource                287978        307
receiver BlueScreen on         287979    MISSING
port state 4 -> 5              289310      22121
AVI infoframe                  289420      22241
signal valid                   290042      22841
CallbackOfSignalChange         290042      22841
UpdateWce                      290061      22860
capture window                 290062      22861
capture WriteReg               290064    MISSING
NR WriteReg                    290064      22863
update_onoff                   290064    MISSING
receiver unmuted               290064      22863
NotifySignalChange             290065      22864
ARM Wce_SetWindow              290070    MISSING
ARM DisableBlackScreen         290229    MISSING

first reference milestone missing from ours: receiver BlueScreen on

reference-only record shapes (83):
     3  crtc: active
     2  hal: source_id              = kHalSourceID_HDMI_#
     2  hal: frame_rate_x#        = #
     2  hal: b_interlace            = #
     2  hal: color_space            = kHalColorSpace_BT#
     2  hal: resolution.h_size      = #
     2  hal: resolution.v_size      = #
     2  hal: hdr_mode               = kHalHdrScheme_Sdr
     2  hal: b_full_range           = #
     2  hal: b_dvi_mode             = #
     2  hal: atv_uid                = #
     2  hdmi_driver: HdmiRx_SendHPDCMD port# cmd=# tick=#
     2  hal: THal_Vp_DisableBlackScreen() ENTER
     2  app: OnHalMiscDisableBlackScreen
     2  bs: DisableBlueScreen, disable blue screen, Handle: #[level: #, id: #], Name: hal, Tag: OnHalMiscDisableBlackScreen
     2  hal: THal_Vp_DisableBlackScreen() LEAVE
     1  frl: set_freerun_flag: # - true
     1  frl: enter_stm_no_signal : #
     1  frl: update_crtc
     1  crtc: force_freerun : true
     1  crtc: force_freerun : false
     1  crtc: set_signal_frame_rate : #
     1  crtc: load_panel_timing
     1  crtc: _load_main_crtc_cfg
     1  crtc: _load_panel_crtc_cfg
     1  crtc: panel crtc is NOT enabled!
     1  crtc: write_registers
     1  crtc: swpll_stop
     1  crtc: hwpll_stop
     1  crtc: crtc is NOT eabled !
     1  hdmirx: HDMIRX Send BlueScreen, bON=#
     1  hal: signal_id              = kHalSignalID_NONE
     1  hal: color_format           = kHalColorFormat_YUV#_#
     1  hdmirx: port id=# HDP_Req=# HPDState=# tick=#
     1  hal: Thal_Vp_SetBacklightLevel() ENTER
     1  app: OnHalBacklightLevelChange
     1  hal: Thal_Vp_SetBacklightLevel() LEAVE
     1  hal: THal_Vp_SetWhiteBalance() ENTER
     1  app: OnHalPqWhiteBalanceChange
     1  hal: THal_Vp_SetWhiteBalance() LEAVE
```

## nosignal: firmware log against stock 10-07

```
reference: 297 records, ticks 287978..290230
ours:      315 records, ticks 307..196417

milestone                   reference       ours
SetSource(3)                   287978        307
AppTopSetSource                287978        307
receiver BlueScreen on         287979    MISSING
port state 4 -> 5              289310      22121
AVI infoframe                  289420      22241
signal valid                   290042      22841
CallbackOfSignalChange         290042      22841
UpdateWce                      290061      22860
capture window                 290062      22861
capture WriteReg               290064      22863
NR WriteReg                    290064      22863
update_onoff                   290064      22863
receiver unmuted               290064      22863
NotifySignalChange             290065      22864
ARM Wce_SetWindow              290070    MISSING
ARM DisableBlackScreen         290229    MISSING

first reference milestone missing from ours: receiver BlueScreen on

reference-only record shapes (71):
     3  crtc: active
     2  hal: source_id              = kHalSourceID_HDMI_#
     2  hal: frame_rate_x#        = #
     2  hal: b_interlace            = #
     2  hal: color_space            = kHalColorSpace_BT#
     2  hal: resolution.h_size      = #
     2  hal: resolution.v_size      = #
     2  hal: hdr_mode               = kHalHdrScheme_Sdr
     2  hal: b_full_range           = #
     2  hal: b_dvi_mode             = #
     2  hal: atv_uid                = #
     2  hdmi_driver: HdmiRx_SendHPDCMD port# cmd=# tick=#
     2  hal: THal_Vp_DisableBlackScreen() ENTER
     2  app: OnHalMiscDisableBlackScreen
     2  bs: DisableBlueScreen, disable blue screen, Handle: #[level: #, id: #], Name: hal, Tag: OnHalMiscDisableBlackScreen
     2  hal: THal_Vp_DisableBlackScreen() LEAVE
     1  frl: set_freerun_flag: # - true
     1  frl: enter_stm_no_signal : #
     1  frl: update_crtc
     1  crtc: force_freerun : true
     1  crtc: force_freerun : false
     1  crtc: set_signal_frame_rate : #
     1  crtc: load_panel_timing
     1  crtc: _load_main_crtc_cfg
     1  crtc: _load_panel_crtc_cfg
     1  crtc: panel crtc is NOT enabled!
     1  crtc: write_registers
     1  crtc: swpll_stop
     1  crtc: hwpll_stop
     1  crtc: crtc is NOT eabled !
     1  hdmirx: HDMIRX Send BlueScreen, bON=#
     1  hal: signal_id              = kHalSignalID_NONE
     1  hal: color_format           = kHalColorFormat_YUV#_#
     1  hdmirx: port id=# HDP_Req=# HPDState=# tick=#
     1  hal: Thal_Vp_SetBacklightLevel() ENTER
     1  app: OnHalBacklightLevelChange
     1  hal: Thal_Vp_SetBacklightLevel() LEAVE
     1  hal: THal_Vp_SetWhiteBalance() ENTER
     1  app: OnHalPqWhiteBalanceChange
     1  hal: THal_Vp_SetWhiteBalance() LEAVE
```

## relocked: firmware log against stock 10-07

```
reference: 297 records, ticks 287978..290230
ours:      487 records, ticks 307..216231

milestone                   reference       ours
SetSource(3)                   287978        307
AppTopSetSource                287978        307
receiver BlueScreen on         287979    MISSING
port state 4 -> 5              289310      22121
AVI infoframe                  289420      22241
signal valid                   290042      22841
CallbackOfSignalChange         290042      22841
UpdateWce                      290061      22860
capture window                 290062      22861
capture WriteReg               290064      22863
NR WriteReg                    290064      22863
update_onoff                   290064      22863
receiver unmuted               290064      22863
NotifySignalChange             290065      22864
ARM Wce_SetWindow              290070    MISSING
ARM DisableBlackScreen         290229    MISSING

first reference milestone missing from ours: receiver BlueScreen on

reference-only record shapes (71):
     3  crtc: active
     2  hal: source_id              = kHalSourceID_HDMI_#
     2  hal: frame_rate_x#        = #
     2  hal: b_interlace            = #
     2  hal: color_space            = kHalColorSpace_BT#
     2  hal: resolution.h_size      = #
     2  hal: resolution.v_size      = #
     2  hal: hdr_mode               = kHalHdrScheme_Sdr
     2  hal: b_full_range           = #
     2  hal: b_dvi_mode             = #
     2  hal: atv_uid                = #
     2  hdmi_driver: HdmiRx_SendHPDCMD port# cmd=# tick=#
     2  hal: THal_Vp_DisableBlackScreen() ENTER
     2  app: OnHalMiscDisableBlackScreen
     2  bs: DisableBlueScreen, disable blue screen, Handle: #[level: #, id: #], Name: hal, Tag: OnHalMiscDisableBlackScreen
     2  hal: THal_Vp_DisableBlackScreen() LEAVE
     1  frl: set_freerun_flag: # - true
     1  frl: enter_stm_no_signal : #
     1  frl: update_crtc
     1  crtc: force_freerun : true
     1  crtc: force_freerun : false
     1  crtc: set_signal_frame_rate : #
     1  crtc: load_panel_timing
     1  crtc: _load_main_crtc_cfg
     1  crtc: _load_panel_crtc_cfg
     1  crtc: panel crtc is NOT enabled!
     1  crtc: write_registers
     1  crtc: swpll_stop
     1  crtc: hwpll_stop
     1  crtc: crtc is NOT eabled !
     1  hdmirx: HDMIRX Send BlueScreen, bON=#
     1  hal: signal_id              = kHalSignalID_NONE
     1  hal: color_format           = kHalColorFormat_YUV#_#
     1  hdmirx: port id=# HDP_Req=# HPDState=# tick=#
     1  hal: Thal_Vp_SetBacklightLevel() ENTER
     1  app: OnHalBacklightLevelChange
     1  hal: Thal_Vp_SetBacklightLevel() LEAVE
     1  hal: THal_Vp_SetWhiteBalance() ENTER
     1  app: OnHalPqWhiteBalanceChange
     1  hal: THal_Vp_SetWhiteBalance() LEAVE
```

## Registers that differ between snapshots

```
register locked nosignal relocked
afbd+0b8 000F01FA 000650AB 000D9028
afbd+0bc 00000EAD 00002EE4 00003382
afbd+30c 0080C258 00804258 00804258
afbd+320 4C7ED000 4C3EF000 4C3EF000
afbd+324 4CDEA000 4C9EC000 4C9EC000
detn+83c 00000F00 00000F04 00000F04
route+168 0C000000 F1000000 37000000
```

