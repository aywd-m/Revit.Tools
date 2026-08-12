# -*- coding: utf-8 -*-
"""
Kidzink Sheet Export - Wizard UI (script.py side)
================================================================
Drives window.xaml. 3-STEP structure:

  Step 0 - Sheet Source     (schedule/list picker)
  Step 1 - Profile          (pick/new/delete profile; "Edit Profile" toggle
                              folds out Parameters + Separators side-by-side —
                              this replaces the old standalone Steps 3/4)
  Step 2 - Export Settings

Paste/import this into the top of script.py, after building:
  - param_names      (list[str])
  - all_profiles     (dict[str, list[str]])   profile_name -> ordered param list
  - preselected      (list[str])              params in current profile, in order
  - SEP_OPTS         (list[str])               e.g. ["-", "_", "(none)"]
  - format_opts / pdf_quality / pdf_processing / dwg_version / dwfx_quality option lists
  - _folder_opts     (list[str] or empty)

Revit 2025 | pyRevit | IronPython 2.7
"""
import os
import System
from System.Windows import Visibility, RoutedEventHandler, MessageBox, MessageBoxButton, MessageBoxResult, MessageBoxImage, GridLength, GridUnitType, UIElement, DataObject, DragDrop, DragDropEffects, SystemParameters, DragEventHandler, GiveFeedbackEventHandler, Thickness
from System.Windows.Input import Keyboard, ModifierKeys, MouseButtonEventHandler, MouseEventHandler, MouseButtonState
from System.Windows.Controls import CheckBox, ComboBox, DataGridRow, TextBox, TextChangedEventHandler, Border, Button, ItemsControl, TextBlock
from System.Windows.Controls.Primitives import ButtonBase
from System.Windows.Media import VisualTreeHelper
from System.Windows.Media.Imaging import BitmapImage, BitmapCacheOption
from System.Windows.Markup import XamlReader
import clr
clr.AddReference("System.Windows.Forms")
import System.Windows.Forms as WinForms
from pyrevit import forms

STEP_LABELS = ["Sheet Source", "Profile", "Export Settings", "View Export"]
LAST_STEP = 3   # index of the final step (View Export)


class _ParamRow(object):
    """Bindable row for the parameter checklist (Edit Profile fold-out)."""
    def __init__(self, name, checked):
        self.Name = name
        self.IsChecked = checked


_DROP_HIGHLIGHT_BG = System.Windows.Media.SolidColorBrush(
    System.Windows.Media.Color.FromRgb(0xFD, 0xEA, 0xEA))
_DROP_HIGHLIGHT_BORDER = System.Windows.Media.SolidColorBrush(
    System.Windows.Media.Color.FromRgb(0xE4, 0x3C, 0x2F))

# Export Settings dropdowns (KzkComboToggle style): dark grey by default,
# red the moment the user picks anything other than the default value.
_COMBO_DEFAULT_BG = System.Windows.Media.SolidColorBrush(
    System.Windows.Media.Color.FromRgb(0x80, 0x80, 0x80))
_COMBO_CHANGED_BG = System.Windows.Media.SolidColorBrush(
    System.Windows.Media.Color.FromRgb(0xE4, 0x3C, 0x2F))


class _SepRow(object):
    """Bindable row for the separator DataGrid (Edit Profile fold-out).
    Label is the display text ("N. ParamName"), recomputed whenever rows are
    reordered; Name is the underlying parameter name, stable across reorders
    and used as the key for preserving each row's chosen separator.

    Plain object — an INotifyPropertyChanged rewrite was tried here and had
    to be reverted: it broke rendering entirely (every row displayed blank,
    including Label/Parameter text that has nothing to do with the binding
    issue), so the interface implementation itself was faulty. Instead, the
    Separator ComboBox's write-back is handled explicitly in code via the
    confirmed-working SelectionChanged handler (see _on_sep_combo_changed),
    bypassing WPF's TwoWay binding write direction entirely rather than
    depending on it."""
    def __init__(self, name, sep_options, separator):
        self.Name = name
        self.Label = name   # placeholder; renumbered immediately after creation
        self.OrderNum = ""  # placeholder; set by _renumber_sep_labels — own column now
        self.IsLastRow = False  # placeholder; set by _renumber_sep_labels
        # Own copy, not a shared reference — a custom separator typed for
        # THIS row must not leak into every other row's dropdown options.
        self.SepOptions = list(sep_options)
        self.Separator = separator
        # If this row's actual (e.g. loaded-from-profile) separator is a
        # custom value not already in the standard options, add it now so
        # the ComboBox can display/select it immediately rather than
        # appearing blank until the user re-picks something.
        if separator not in self.SepOptions:
            insert_at = (self.SepOptions.index("Custom...")
                         if "Custom..." in self.SepOptions else len(self.SepOptions))
            self.SepOptions.insert(insert_at, separator)


class _ParamSegment(object):
    """One piece of a profile's displayed parameter string — either a
    parameter name (IsMissing set if it doesn't exist in the current model)
    or a plain separator character, which is never marked missing.
    IsSeparator distinguishes the two so the display template can box only
    the parameter names as chips, leaving separators as plain connectors."""
    def __init__(self, text, is_missing=False, is_separator=False):
        self.Text = text
        self.IsMissing = is_missing
        self.IsSeparator = is_separator


class _ProfileRow(object):
    def __init__(self, name, param_string, segments=None):
        self.Name = name
        self.ParamString = param_string
        self.Segments = segments if segments is not None else [_ParamSegment(param_string)]
        # Inline-editor state — only ever True for the one row currently
        # being edited. EditRows is set to the SAME list object as
        # self.sep_rows (not a copy), so the chips rendered here and the
        # data Save Profile reads from are literally the same objects.
        self.IsEditing = False
        self.EditRows = None


_COLLECTION_NONE_LABEL = "(none)"

def _display_collection(name):
    """Map script.py's internal '_NoSheetCollection' sentinel (used for
    folder naming) to a friendly label for the picker — the wizard has no
    reason to know about that sentinel string."""
    return _COLLECTION_NONE_LABEL if (not name or name == "_NoSheetCollection") else name


class _SheetRow(object):
    """Bindable row for the By Selection sheet checklist (Step 0)."""
    def __init__(self, number, name, collection, checked=False):
        self.Number = number
        self.Name = name
        self.Collection = collection
        self.IsChecked = checked


class _SheetGroupRow(object):
    """Bindable group row for the Project-Browser-style tree in Step 0 — one
    per Sheet Collection, containing its member _SheetRow objects. HeaderText
    and Chevron are plain recomputed strings (not Python @property values):
    WPF binding to IronPython objects in this codebase always uses plain
    instance attributes refreshed via ItemsControl.Items.Refresh(), matching
    every other bindable row class here (never rely on live property
    evaluation via binding)."""
    def __init__(self, name, sheets):
        self.Name = name
        self.Sheets = sheets
        self.IsExpanded = True
        self.IsChecked = False
        self.HeaderText = ""
        self.Chevron = u"\u25BE"


class _FormatRow(object):
    """Bindable row for the Output Format checklist (Step 2 Export Settings).
    Replaces the old single-select CboExportFormat combo — any combination of
    formats can now be ticked independently instead of picking from a
    hard-coded list of every combinatorial string (e.g. "PDF + DWG")."""
    def __init__(self, name, checked=False):
        self.Name = name
        self.IsChecked = checked


class _LinkRow(object):
    """Bindable row for the Reload Links checklist (Step 2 pre-export section)."""
    def __init__(self, name, path_display, checked=False):
        self.Name = name
        self.PathDisplay = path_display
        self.IsChecked = checked


class _ViewRow(object):
    """Bindable row for the View Export checklist (Step 3)."""
    def __init__(self, name, view_type_name, is_exportable=True, view=None, checked=False):
        self.Name = name
        self.ViewTypeName = view_type_name
        self.IsExportable = is_exportable
        self.View = view
        self.IsChecked = checked


# ----------------------------------------------------------------------
# WPF Input Dialog – replaces VB InputBox
# ----------------------------------------------------------------------
_INPUT_DIALOG_XAML = u"""<Window
    xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
    xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
    Title="Input"
    Width="420" SizeToContent="Height"
    WindowStartupLocation="CenterOwner" ResizeMode="NoResize"
    Background="#C0C0C0">

  <Window.Resources>
    <Style x:Key="StBtn" TargetType="Button">
      <Setter Property="Background" Value="#E43C2F"/>
      <Setter Property="Foreground" Value="#FFFFFF"/>
      <Setter Property="BorderThickness" Value="0"/>
      <Setter Property="Padding" Value="14,6"/>
      <Setter Property="FontSize" Value="12"/>
      <Setter Property="FontWeight" Value="SemiBold"/>
      <Setter Property="Cursor" Value="Hand"/>
      <Setter Property="Height" Value="30"/>
      <Setter Property="Width" Value="90"/>
      <Setter Property="Template">
        <Setter.Value>
          <ControlTemplate TargetType="Button">
            <Border Background="{TemplateBinding Background}" CornerRadius="4"
                    Padding="{TemplateBinding Padding}">
              <ContentPresenter HorizontalAlignment="Center" VerticalAlignment="Center"/>
            </Border>
            <ControlTemplate.Triggers>
              <Trigger Property="IsMouseOver" Value="True">
                <Setter Property="Background" Value="#C73652"/>
              </Trigger>
              <Trigger Property="IsPressed" Value="True">
                <Setter Property="Background" Value="#A02040"/>
              </Trigger>
            </ControlTemplate.Triggers>
          </ControlTemplate>
        </Setter.Value>
      </Setter>
    </Style>

    <Style x:Key="StBtnGhost" TargetType="Button" BasedOn="{StaticResource StBtn}">
      <Setter Property="Background" Value="#808080"/>
      <Style.Triggers>
        <Trigger Property="IsMouseOver" Value="True">
          <Setter Property="Background" Value="#666666"/>
        </Trigger>
      </Style.Triggers>
    </Style>

    <Style x:Key="StText" TargetType="TextBox">
      <Setter Property="Background" Value="#FFFFFF"/>
      <Setter Property="Foreground" Value="#333333"/>
      <Setter Property="BorderBrush" Value="#999999"/>
      <Setter Property="BorderThickness" Value="1"/>
      <Setter Property="Padding" Value="8,5"/>
      <Setter Property="FontSize" Value="12"/>
      <Setter Property="CaretBrush" Value="#333333"/>
    </Style>
  </Window.Resources>

  <Grid>
    <Grid.RowDefinitions>
      <RowDefinition Height="48"/>
      <RowDefinition Height="Auto"/>
    </Grid.RowDefinitions>

    <!-- Header -->
    <Border Grid.Row="0" Background="#E43C2F">
      <DockPanel Margin="16,0">
        <TextBlock x:Name="TitleText" DockPanel.Dock="Left" Text="Input" Foreground="#FFFFFF"
                   FontSize="15" FontWeight="Bold" VerticalAlignment="Center"/>
      </DockPanel>
    </Border>

    <!-- Body -->
    <StackPanel Grid.Row="1" Margin="20,18,20,18">
      <TextBlock x:Name="PromptText" Text="Enter value:" Foreground="#333333" FontSize="12" Margin="0,0,0,8"/>
      <TextBox x:Name="InputBox" Style="{StaticResource StText}" Margin="0,0,0,16"/>
      <StackPanel Orientation="Horizontal" HorizontalAlignment="Right">
        <Button x:Name="BtnCancel" Content="Cancel" Style="{StaticResource StBtnGhost}" Margin="0,0,8,0"/>
        <Button x:Name="BtnOK" Content="OK" Style="{StaticResource StBtn}"/>
      </StackPanel>
    </StackPanel>
  </Grid>
</Window>
"""

class InputDialog(object):
    """Simple WPF input dialog. Show() returns the entered string, or None if cancelled."""
    def __init__(self, owner, title, prompt, default_text=""):
        self.win = XamlReader.Parse(_INPUT_DIALOG_XAML)
        try:
            self.win.Owner = owner
        except Exception:
            pass
        self.win.Title = title
        self.win.FindName("TitleText").Text = title
        self.win.FindName("PromptText").Text = prompt
        self.txt = self.win.FindName("InputBox")
        self.txt.Text = default_text
        self.txt.Focus()
        self.win.FindName("BtnOK").Click += self._on_ok
        self.win.FindName("BtnCancel").Click += self._on_cancel
        self.win.KeyDown += self._on_key_down
        self.result = None

    def _on_ok(self, sender, args):
        self.result = self.txt.Text
        self.win.Close()

    def _on_cancel(self, sender, args):
        self.result = None
        self.win.Close()

    def _on_key_down(self, sender, args):
        if args.Key == System.Windows.Input.Key.Enter:
            self._on_ok(None, None)
        elif args.Key == System.Windows.Input.Key.Escape:
            self._on_cancel(None, None)

    def show(self):
        self.win.ShowDialog()
        return self.result


# ----------------------------------------------------------------------
# Settings dialog — "Schedule Export"
#
# Built from an inline XAML string (no separate file needed for a dialog
# this small — matches the Kidzink house pattern of XamlReader.Load for
# lightweight utility windows). Lets the user enable a scheduled export,
# picking a Date + Time (HH:mm). Cancel discards changes; OK stores them
# back onto the wizard.
# ----------------------------------------------------------------------
_SETTINGS_XAML = u"""<Window
    xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
    xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
    Title="Export Settings"
    Width="400" SizeToContent="Height"
    WindowStartupLocation="CenterOwner" ResizeMode="NoResize"
    Background="#C0C0C0">

  <Window.Resources>
    <!-- ═══ Styles mirrored from the main wizard window.xaml so this
         popup reads as part of the same tool, not a stock WPF dialog ═══ -->
    <Style x:Key="StBtn" TargetType="Button">
      <Setter Property="Background"      Value="#E43C2F"/>
      <Setter Property="Foreground"      Value="#FFFFFF"/>
      <Setter Property="BorderThickness" Value="0"/>
      <Setter Property="Padding"         Value="14,6"/>
      <Setter Property="FontSize"        Value="12"/>
      <Setter Property="FontWeight"      Value="SemiBold"/>
      <Setter Property="Cursor"          Value="Hand"/>
      <Setter Property="Height"          Value="30"/>
      <Setter Property="Width"           Value="90"/>
      <Setter Property="Template">
        <Setter.Value>
          <ControlTemplate TargetType="Button">
            <Border Background="{TemplateBinding Background}" CornerRadius="4"
                    Padding="{TemplateBinding Padding}">
              <ContentPresenter HorizontalAlignment="Center" VerticalAlignment="Center"/>
            </Border>
            <ControlTemplate.Triggers>
              <Trigger Property="IsMouseOver" Value="True">
                <Setter Property="Background" Value="#C73652"/>
              </Trigger>
              <Trigger Property="IsPressed" Value="True">
                <Setter Property="Background" Value="#A02040"/>
              </Trigger>
            </ControlTemplate.Triggers>
          </ControlTemplate>
        </Setter.Value>
      </Setter>
    </Style>

    <Style x:Key="StBtnGhost" TargetType="Button" BasedOn="{StaticResource StBtn}">
      <Setter Property="Background" Value="#808080"/>
      <Style.Triggers>
        <Trigger Property="IsMouseOver" Value="True">
          <Setter Property="Background" Value="#666666"/>
        </Trigger>
      </Style.Triggers>
    </Style>

    <Style x:Key="StCheck" TargetType="CheckBox">
      <Setter Property="Foreground"  Value="#333333"/>
      <Setter Property="FontSize"    Value="12"/>
      <Setter Property="Margin"      Value="0,0,0,4"/>
      <Setter Property="Padding"     Value="10,0,0,0"/>
      <Setter Property="Template">
        <Setter.Value>
          <ControlTemplate TargetType="CheckBox">
            <StackPanel Orientation="Horizontal">
              <Border x:Name="Box" Width="16" Height="16" CornerRadius="2"
                      BorderBrush="#999999" BorderThickness="1" Background="#FFFFFF">
                <Path x:Name="Tick" Data="M2,7 L6,11 L14,2" Stroke="#FFFFFF"
                      StrokeThickness="2" Visibility="Collapsed"
                      StrokeStartLineCap="Round" StrokeEndLineCap="Round"
                      StrokeLineJoin="Round"/>
              </Border>
              <ContentPresenter Margin="{TemplateBinding Padding}" VerticalAlignment="Center"/>
            </StackPanel>
            <ControlTemplate.Triggers>
              <Trigger Property="IsChecked" Value="True">
                <Setter TargetName="Box" Property="Background" Value="#E43C2F"/>
                <Setter TargetName="Box" Property="BorderBrush" Value="#E43C2F"/>
                <Setter TargetName="Tick" Property="Visibility" Value="Visible"/>
              </Trigger>
            </ControlTemplate.Triggers>
          </ControlTemplate>
        </Setter.Value>
      </Setter>
    </Style>

    <Style x:Key="StTextBox" TargetType="TextBox">
      <Setter Property="Background"      Value="#FFFFFF"/>
      <Setter Property="Foreground"      Value="#333333"/>
      <Setter Property="FontWeight"      Value="Normal"/>
      <Setter Property="FontSize"        Value="12"/>
      <Setter Property="BorderBrush"     Value="Transparent"/>
      <Setter Property="BorderThickness" Value="0"/>
    </Style>

    <Style x:Key="StSpin" TargetType="RepeatButton">
      <Setter Property="Background"      Value="#808080"/>
      <Setter Property="Foreground"      Value="#FFFFFF"/>
      <Setter Property="BorderThickness" Value="0"/>
      <Setter Property="FontSize"        Value="7"/>
      <Setter Property="Focusable"       Value="False"/>
      <Setter Property="Cursor"          Value="Hand"/>
      <Setter Property="Template">
        <Setter.Value>
          <ControlTemplate TargetType="RepeatButton">
            <Border x:Name="SpBd" Background="{TemplateBinding Background}">
              <ContentPresenter HorizontalAlignment="Center" VerticalAlignment="Center"/>
            </Border>
            <ControlTemplate.Triggers>
              <Trigger Property="IsMouseOver" Value="True">
                <Setter TargetName="SpBd" Property="Background" Value="#666666"/>
              </Trigger>
            </ControlTemplate.Triggers>
          </ControlTemplate>
        </Setter.Value>
      </Setter>
    </Style>

    <!-- Flat calendar toggle button — same grey as the hour/minute spinner
         buttons, with a hand-drawn calendar glyph so the icon color is
         guaranteed regardless of Windows theme (unlike DatePicker's stock
         button, whose glyph color is theme-controlled, not Foreground). -->
    <Style x:Key="StCalBtn" TargetType="Button">
      <Setter Property="Background"      Value="#808080"/>
      <Setter Property="BorderThickness" Value="0"/>
      <Setter Property="Cursor"          Value="Hand"/>
      <Setter Property="Focusable"       Value="False"/>
      <Setter Property="Template">
        <Setter.Value>
          <ControlTemplate TargetType="Button">
            <Border x:Name="CalBd" Background="{TemplateBinding Background}">
              <Path Stretch="Uniform" Width="14" Height="14"
                    Stroke="#FFFFFF" StrokeThickness="1.6"
                    StrokeStartLineCap="Round" StrokeEndLineCap="Round"
                    Data="M3,4 L21,4 A1.5,1.5 0 0 1 22.5,5.5 L22.5,20 A1.5,1.5 0 0 1 21,21.5 L3,21.5 A1.5,1.5 0 0 1 1.5,20 L1.5,5.5 A1.5,1.5 0 0 1 3,4 Z M1.5,9 L22.5,9 M7,2.5 L7,5.5 M17,2.5 L17,5.5"/>
            </Border>
            <ControlTemplate.Triggers>
              <Trigger Property="IsMouseOver" Value="True">
                <Setter TargetName="CalBd" Property="Background" Value="#666666"/>
              </Trigger>
            </ControlTemplate.Triggers>
          </ControlTemplate>
        </Setter.Value>
      </Setter>
    </Style>

    <Style x:Key="StHint" TargetType="TextBlock">
      <Setter Property="FontSize"      Value="10"/>
      <Setter Property="Foreground"    Value="#888888"/>
      <Setter Property="TextWrapping"  Value="Wrap"/>
      <Setter Property="Margin"        Value="0,4,0,14"/>
    </Style>

    <Style x:Key="StSectionLabel" TargetType="TextBlock">
      <Setter Property="FontWeight"  Value="Bold"/>
      <Setter Property="FontSize"    Value="12"/>
      <Setter Property="Foreground"  Value="#16242E"/>
      <Setter Property="Margin"      Value="0,0,0,10"/>
    </Style>
  </Window.Resources>

  <Grid>
    <Grid.RowDefinitions>
      <RowDefinition Height="48"/>
      <RowDefinition Height="Auto"/>
    </Grid.RowDefinitions>

    <!-- ═══ HEADER BAR — matches the main wizard's red header ═══ -->
    <Border Grid.Row="0" Background="#E43C2F">
      <DockPanel Margin="16,0">
        <TextBlock DockPanel.Dock="Left" Text="Export Settings" Foreground="#FFFFFF"
                   FontSize="15" FontWeight="Bold" VerticalAlignment="Center"/>
      </DockPanel>
    </Border>

    <!-- ═══ BODY ═══ -->
    <StackPanel Grid.Row="1" Margin="20,18,20,18">

      <TextBlock Text="Schedule Export" Style="{StaticResource StSectionLabel}"/>
      <CheckBox x:Name="ChkEnableSchedule" Content="Enable scheduled export"
                Style="{StaticResource StCheck}" FontWeight="SemiBold" Margin="0,0,0,14"/>

      <StackPanel Orientation="Horizontal" Margin="0,0,0,10">
        <TextBlock Text="Date:" Width="90" VerticalAlignment="Center" Foreground="#333333" FontSize="12"/>
        <Grid>
          <Border x:Name="DateFieldBorder" BorderBrush="#999999" BorderThickness="1"
                  Background="#FFFFFF" Height="30" Width="122">
            <DockPanel LastChildFill="True">
              <Button x:Name="BtnCalendarToggle" DockPanel.Dock="Right" Width="28" Height="28"
                      Margin="0,1,1,1" Style="{StaticResource StCalBtn}"/>
              <TextBlock x:Name="TxtDateDisplay" VerticalAlignment="Center" Margin="8,0,0,0"
                         FontSize="12" Foreground="#333333" Text=""/>
            </DockPanel>
          </Border>
          <Popup x:Name="DatePopup" PlacementTarget="{Binding ElementName=DateFieldBorder}"
                 Placement="Bottom" StaysOpen="False">
            <Border Background="#FFFFFF" BorderBrush="#999999" BorderThickness="1">
              <Calendar x:Name="CalWidget"/>
            </Border>
          </Popup>
        </Grid>
      </StackPanel>

      <StackPanel Orientation="Horizontal" Margin="0,0,0,4">
        <TextBlock Text="Time (HH:mm):" Width="90" VerticalAlignment="Center" Foreground="#333333" FontSize="12"/>
        <Border BorderBrush="#999999" BorderThickness="1" Background="#FFFFFF" Height="30" Padding="8,0">
          <StackPanel Orientation="Horizontal" VerticalAlignment="Center">
            <TextBox x:Name="TxtHour" Width="26" Text="17" TextAlignment="Center"
                     Style="{StaticResource StTextBox}" VerticalAlignment="Center"/>
            <StackPanel Orientation="Vertical" VerticalAlignment="Center" Margin="2,0,0,0">
              <RepeatButton x:Name="BtnHourUp"   Content="▲" Width="16" Height="11" Style="{StaticResource StSpin}"/>
              <RepeatButton x:Name="BtnHourDown" Content="▼" Width="16" Height="11" Style="{StaticResource StSpin}"/>
            </StackPanel>
            <TextBlock Text=":" VerticalAlignment="Center" Margin="6,0" FontSize="12" Foreground="#333333"/>
            <TextBox x:Name="TxtMinute" Width="26" Text="00" TextAlignment="Center"
                     Style="{StaticResource StTextBox}" VerticalAlignment="Center"/>
            <StackPanel Orientation="Vertical" VerticalAlignment="Center" Margin="2,0,0,0">
              <RepeatButton x:Name="BtnMinuteUp"   Content="▲" Width="16" Height="11" Style="{StaticResource StSpin}"/>
              <RepeatButton x:Name="BtnMinuteDown" Content="▼" Width="16" Height="11" Style="{StaticResource StSpin}"/>
            </StackPanel>
          </StackPanel>
        </Border>
      </StackPanel>
      <TextBlock Style="{StaticResource StHint}"
                 Text="When enabled, clicking Export will ask for an output folder, confirm the scheduled time, then wait until that time before exporting with the settings from this wizard. Revit must stay open."/>

      <Border BorderBrush="#A0A0A0" BorderThickness="0,1,0,0" Margin="0,0,0,16"/>

      <TextBlock Text="Report" Style="{StaticResource StSectionLabel}"/>
      <CheckBox x:Name="ChkIncludeReport" Content="Include HTML report after export"
                Style="{StaticResource StCheck}" FontWeight="SemiBold" Margin="0,0,0,4"/>
      <TextBlock Style="{StaticResource StHint}" Margin="0,4,0,18"
                 Text="When unchecked, no HTML report file is generated or saved — only the export itself runs."/>

      <StackPanel Orientation="Horizontal" HorizontalAlignment="Right">
        <Button x:Name="BtnSettingsCancel" Content="Cancel" Style="{StaticResource StBtnGhost}" Margin="0,0,8,0"/>
        <Button x:Name="BtnSettingsOK" Content="OK" Style="{StaticResource StBtn}"/>
      </StackPanel>
    </StackPanel>
  </Grid>
</Window>
"""


class _SettingsDialog(object):
    """Modal Schedule Export dialog. .show() returns a dict on OK, None on
    Cancel/closed-without-OK.

    Date/time default to the moment this dialog is opened (System.DateTime.Now)
    unless a schedule was already configured earlier in this session, in which
    case those saved values are shown instead."""

    def __init__(self, owner, enabled, sched_date, sched_time, include_report):
        self.win = XamlReader.Parse(_SETTINGS_XAML)
        try:
            self.win.Owner = owner
        except Exception:
            pass

        self.chk           = self.win.FindName("ChkEnableSchedule")
        self.date_border   = self.win.FindName("DateFieldBorder")
        self.date_popup    = self.win.FindName("DatePopup")
        self.cal_widget    = self.win.FindName("CalWidget")
        self.txt_date      = self.win.FindName("TxtDateDisplay")
        self.btn_cal       = self.win.FindName("BtnCalendarToggle")
        self.txt_hour      = self.win.FindName("TxtHour")
        self.txt_minute    = self.win.FindName("TxtMinute")
        self.btn_hour_up   = self.win.FindName("BtnHourUp")
        self.btn_hour_dn   = self.win.FindName("BtnHourDown")
        self.btn_min_up    = self.win.FindName("BtnMinuteUp")
        self.btn_min_dn    = self.win.FindName("BtnMinuteDown")
        self.chk_report    = self.win.FindName("ChkIncludeReport")
        self.btn_ok        = self.win.FindName("BtnSettingsOK")
        self.btn_cancel    = self.win.FindName("BtnSettingsCancel")

        self.chk.IsChecked = bool(enabled)
        self.chk_report.IsChecked = bool(include_report)

        # Default to "now" (the moment the dialog is opened) unless a
        # schedule was already set earlier in this session.
        now = System.DateTime.Now
        use_date = sched_date if sched_date is not None else now.Date
        if sched_time:
            try:
                hh, mm = sched_time.split(":")
                use_hour, use_minute = int(hh), int(mm)
            except Exception:
                use_hour, use_minute = now.Hour, now.Minute
        else:
            use_hour, use_minute = now.Hour, now.Minute

        self._selected_date = use_date
        try:
            self.cal_widget.SelectedDate = use_date
            self.cal_widget.DisplayDate = use_date
        except Exception:
            pass
        self.txt_date.Text   = use_date.ToString("dd/MM/yyyy")
        self.txt_hour.Text   = "{:02d}".format(use_hour)
        self.txt_minute.Text = "{:02d}".format(use_minute)

        self.result = None
        self.btn_ok.Click += self._on_ok
        self.btn_cancel.Click += self._on_cancel
        self.btn_cal.Click += self._on_calendar_toggle
        self.cal_widget.SelectedDatesChanged += self._on_calendar_date_changed
        self.btn_hour_up.Click += lambda s, e: self._bump(self.txt_hour, 1, 23)
        self.btn_hour_dn.Click += lambda s, e: self._bump(self.txt_hour, -1, 23)
        self.btn_min_up.Click  += lambda s, e: self._bump(self.txt_minute, 1, 59)
        self.btn_min_dn.Click  += lambda s, e: self._bump(self.txt_minute, -1, 59)

    def _on_calendar_toggle(self, sender, args):
        self.date_popup.IsOpen = not self.date_popup.IsOpen

    def _on_calendar_date_changed(self, sender, args):
        d = self.cal_widget.SelectedDate
        if d is not None:
            self._selected_date = d
            self.txt_date.Text = d.ToString("dd/MM/yyyy")
        self.date_popup.IsOpen = False

    @staticmethod
    def _bump(txt_box, step, max_val):
        """Increment/decrement a HH or MM text box by step, wrapping around
        0..max_val (inclusive), keeping 2-digit zero-padded display."""
        try:
            val = int((txt_box.Text or "0").strip())
        except ValueError:
            val = 0
        val = (val + step) % (max_val + 1)
        txt_box.Text = "{:02d}".format(val)

    def _on_ok(self, sender, args):
        try:
            hh = int((self.txt_hour.Text or "0").strip()) % 24
        except ValueError:
            hh = 0
        try:
            mm = int((self.txt_minute.Text or "0").strip()) % 60
        except ValueError:
            mm = 0
        self.result = {
            "enabled": bool(self.chk.IsChecked),
            "date": self._selected_date,     # System.DateTime (defaults to "now" if never changed)
            "time": "{:02d}:{:02d}".format(hh, mm),
            "include_report": bool(self.chk_report.IsChecked),
        }
        self.win.Close()

    def _on_cancel(self, sender, args):
        self.result = None
        self.win.Close()

    def show(self):
        self.win.ShowDialog()
        return self.result


class ExportWizardWindow(forms.WPFWindow):

    def __init__(self, xaml_file_name, param_names, all_profiles, preselected,
                 sep_options, profile_name,
                 format_opts, pdf_quality_opts, pdf_processing_opts,
                 dwg_version_opts, folder_opts,
                 schedule_source_opts, sheet_options=None, preselected_sheet_numbers=None,
                 link_options=None, is_workshared=False,
                 dwfx_quality_opts=None, dwf_quality_opts=None, default_formats=None,
                 is_last_used_profile=False, has_links=False, link_provider=None,
                 view_rows_data=None):
        forms.WPFWindow.__init__(self, xaml_file_name)

        # Compute script directory from the XAML file path for logo loading
        self.script_dir = os.path.dirname(xaml_file_name)
        self.logo_path = os.path.join(self.script_dir, "logo.png")

        self.param_names = param_names
        self.all_profiles = all_profiles
        self.sep_options = list(sep_options)
        if "Custom..." not in self.sep_options:
            self.sep_options.append("Custom...")
        self.profile_name = profile_name
        self.is_last_used_profile = is_last_used_profile
        self._last_used_profile_name = profile_name if is_last_used_profile else None
        self.result = None          # final payload set on Export
        self.current_step = 0       # land on Sheet Source
        self.edit_profile_open = False

        # Most-recently-edited order for the profile list — Save/Rename/New
        # all move that profile to the front, so whatever you just touched is
        # always at the top instead of wherever it happens to sort
        # alphabetically. Seeded with the initially active profile first.
        self._profile_mru = [profile_name] + [
            n for n in all_profiles.keys() if n != profile_name]

        # Schedule Export state, set via the Settings dialog (gear icon).
        # date/time start unset (None) so the first time the dialog opens it
        # defaults to "now" rather than a hardcoded time; once the user has
        # opened Settings once, their choice is remembered for the rest of
        # this wizard session.
        self.schedule_settings = {"enabled": False, "date": None, "time": None,
                                   "include_report": True}

        # Manually-arranged parameter order for the filename, set via the
        # Separator grid's Order (up/down) buttons. This is the SOLE source
        # of truth for export order — NOT each parameter's fixed position in
        # the checklist above, which was the root cause of a real bug:
        # whichever parameter happened to sit first in the checklist (e.g.
        # "Sheet Number") always ended up first in the filename regardless
        # of when it was actually ticked. Persists across ticks/unticks:
        # unticked params are removed, newly-ticked ones are appended at the
        # end, and anything already arranged keeps its manually-set position.
        self._param_order = []

        self._load_logo()
        self._wire_step_nav()
        self._populate_sheet_source_step(schedule_source_opts, sheet_options or [],
                                          preselected_sheet_numbers or [])
        self._populate_profile_step()
        self._populate_parameters_step(preselected)
        self._populate_separators_step()
        self._wire_edit_profile_toggle()
        self._populate_export_settings_step(
            format_opts, pdf_quality_opts, pdf_processing_opts,
            dwg_version_opts, folder_opts,
            dwfx_quality_opts or ["Default", "Low", "Medium", "High", "Best"],
            dwf_quality_opts  or ["Default", "Low", "Medium", "High", "Best"],
            default_formats or ["PDF"])
        self._has_links = has_links
        self._link_provider = link_provider
        self._links_loaded = False
        self._populate_pre_export_actions(link_options or [], is_workshared)
        self._populate_view_source(view_rows_data or [], dwg_version_opts)

        self.BtnBack.Click += self._on_back
        self.BtnNext.Click += self._on_next
        self.BtnSettings.Click += self._on_settings_click
        # A WPF Hyperlink does nothing on click by default unless
        # RequestNavigate is handled — without this, "www.kidzink.com" in
        # the footer looked clickable but silently did nothing.
        self.LnkKidzink.RequestNavigate += self._on_kidzink_link_click
        self._show_step(self.current_step)

    def _on_settings_click(self, sender, args):
        dlg = _SettingsDialog(
            self,
            self.schedule_settings.get("enabled", False),
            self.schedule_settings.get("date"),
            self.schedule_settings.get("time", "17:00"),
            self.schedule_settings.get("include_report", True))
        res = dlg.show()
        if res is not None:
            self.schedule_settings = res

    def _on_kidzink_link_click(self, sender, args):
        try:
            System.Diagnostics.Process.Start(System.Diagnostics.ProcessStartInfo(
                args.Uri.AbsoluteUri, UseShellExecute=True))
        except Exception:
            pass
        args.Handled = True

    # ------------------------------------------------------------------
    # Logo (collapsed if logo.png absent, per approved design)
    # ------------------------------------------------------------------
    def _load_logo(self):
        if os.path.isfile(self.logo_path):
            try:
                bmp = BitmapImage()
                bmp.BeginInit()
                bmp.UriSource = System.Uri(self.logo_path)
                bmp.CacheOption = BitmapCacheOption.OnLoad
                bmp.EndInit()
                self.ImgLogo.Source = bmp
                self.ImgLogo.Visibility = Visibility.Visible
            except Exception:
                pass  # stays collapsed on any load failure

    # ------------------------------------------------------------------
    # Step navigation (3 steps now)
    # ------------------------------------------------------------------
    def _wire_step_nav(self):
        self.step_panels = [self.Panel0, self.Panel1, self.Panel2, self.Panel3]
        self.step_buttons = [self.StepBtn0, self.StepBtn1, self.StepBtn2, self.StepBtn3]
        for btn in self.step_buttons:
            btn.Click += self._on_step_click

    def _on_step_click(self, sender, args):
        self._show_step(int(sender.Tag))

    def _on_back(self, sender, args):
        if self.current_step > 0:
            self._show_step(self.current_step - 1)

    def _on_next(self, sender, args):
        if self.current_step < LAST_STEP:
            self._show_step(self.current_step + 1)
        else:
            self._on_export()

    def _show_step(self, index):
        self.current_step = index
        for i, panel in enumerate(self.step_panels):
            panel.Visibility = Visibility.Visible if i == index else Visibility.Collapsed
        for i, btn in enumerate(self.step_buttons):
            if i == index:
                btn.Background = System.Windows.Media.SolidColorBrush(
                    System.Windows.Media.Color.FromRgb(0xE4, 0x3C, 0x2F))
                btn.Foreground = System.Windows.Media.Brushes.White
            elif i < index:
                btn.Background = System.Windows.Media.SolidColorBrush(
                    System.Windows.Media.Color.FromRgb(0xE8, 0xB9, 0xB4))
                btn.Foreground = System.Windows.Media.SolidColorBrush(
                    System.Windows.Media.Color.FromRgb(0x16, 0x24, 0x2E))
            else:
                btn.ClearValue(System.Windows.Controls.Control.BackgroundProperty)
                btn.ClearValue(System.Windows.Controls.Control.ForegroundProperty)
        self.BtnNext.Content = "Export" if index == LAST_STEP else "Next →"
        self.TxtStatus.Text = "Step {} of 4 — {}".format(index + 1, STEP_LABELS[index])

        # Leaving Profile step with Edit Profile open: keep separators in sync
        # with whatever parameters are currently ticked.
        if index != 1 and self.edit_profile_open:
            self.refresh_separators_from_step3()

    # ------------------------------------------------------------------
    # Step 0: Sheet Source (By Selection / By Schedule)
    # ------------------------------------------------------------------
    _SHEET_FILTER_FIELDS = ["Number, Name, or Collection", "Sheet Number", "Sheet Name", "Sheet Collection"]
    _SHEET_FILTER_MODES  = ["Contains", "Does not contain", "Begins with", "Ends with", "Equals"]

    def _populate_sheet_source_step(self, schedule_source_opts, sheet_options,
                                     preselected_sheet_numbers):
        # -- By Schedule sub-panel --
        self.CboScheduleSource.ItemsSource = schedule_source_opts
        if schedule_source_opts:
            self.CboScheduleSource.SelectedIndex = 0

        # -- By Selection sub-panel: grouped Project-Browser-style tree --
        pre_set = set(preselected_sheet_numbers)
        self.sheet_rows = [
            _SheetRow(s["number"], s["name"], _display_collection(s.get("collection")),
                      s["number"] in pre_set)
            for s in sheet_options
        ]

        # Group by collection, preserving first-seen order; "(none)" always
        # goes last regardless of when it was first encountered, matching
        # how Revit's own Project Browser lists unassigned sheets last.
        order = []
        buckets = {}
        for row in self.sheet_rows:
            key = row.Collection
            if key not in buckets:
                buckets[key] = []
                order.append(key)
            buckets[key].append(row)
        if _COLLECTION_NONE_LABEL in order:
            order.remove(_COLLECTION_NONE_LABEL)
            order.append(_COLLECTION_NONE_LABEL)

        self.group_rows = [_SheetGroupRow(name, buckets[name]) for name in order]
        self.IcSheetGroups.ItemsSource = self.group_rows
        self._last_sheet_click = None   # (group, index) for shift+click range-select

        # Filter row: live-as-you-type (TextChanged/SelectionChanged), plus
        # the Apply/Clear buttons remain for explicit control.
        self.CboSheetFilterField.ItemsSource = self._SHEET_FILTER_FIELDS
        self.CboSheetFilterField.SelectedIndex = 0
        self.CboSheetFilterMode.ItemsSource = self._SHEET_FILTER_MODES
        self.CboSheetFilterMode.SelectedIndex = 0
        self.BtnSheetFilterClear.Click += self._on_sheet_filter_clear
        self.TxtSheetFilterValue.TextChanged += self._on_sheet_filter_apply
        self.CboSheetFilterField.SelectionChanged += self._on_sheet_filter_apply
        self.CboSheetFilterMode.SelectionChanged += self._on_sheet_filter_apply

        self.BtnCheckAllSheets.Click     += lambda s, e: self._set_all_sheets_checked(True)
        self.BtnUncheckAllSheets.Click   += lambda s, e: self._set_all_sheets_checked(False)
        self.BtnToggleAllSheets.Click    += lambda s, e: self._toggle_all_sheets_checked()
        self.BtnExpandAllSheets.Click    += lambda s, e: self._set_all_groups_expanded(True)
        self.BtnCollapseAllSheets.Click  += lambda s, e: self._set_all_groups_expanded(False)

        # Bubbling handlers on the outer tree ItemsControl catch every
        # nested control's events regardless of which group/sheet template
        # instance raised them — same pattern as IcFormats/IcParameters
        # elsewhere in this file. Checked/Unchecked fires for BOTH group
        # header checkboxes and individual sheet checkboxes; distinguished
        # inside the handler by the DataContext's type.
        self.IcSheetGroups.AddHandler(
            CheckBox.CheckedEvent, RoutedEventHandler(self._on_sheet_tree_check_changed))
        self.IcSheetGroups.AddHandler(
            CheckBox.UncheckedEvent, RoutedEventHandler(self._on_sheet_tree_check_changed))
        # ButtonBase.Click catches both the chevron Button (expand/collapse)
        # and CheckBox clicks (CheckBox is a ToggleButton -> ButtonBase, used
        # here purely for shift+click range-select bookkeeping) — split by
        # checking the concrete OriginalSource type.
        self.IcSheetGroups.AddHandler(
            ButtonBase.ClickEvent, RoutedEventHandler(self._on_sheet_tree_click))

        self._refresh_sheet_tree()

        # -- Mode toggle: switch which sub-panel is visible --
        self.RbBySchedule.Checked += self._on_source_mode_changed
        self.RbBySelection.Checked += self._on_source_mode_changed
        self._on_source_mode_changed(None, None)   # apply initial state (By Selection)

    def _on_source_mode_changed(self, sender, args):
        by_selection = bool(self.RbBySelection.IsChecked)
        self.SubPanelSchedule.Visibility = Visibility.Collapsed if by_selection else Visibility.Visible
        self.SubPanelSelection.Visibility = Visibility.Visible if by_selection else Visibility.Collapsed

    # ------------------------------------------------------------------
    # Filter (Revit-style: field + contains/does not contain/begins/ends/equals)
    # ------------------------------------------------------------------
    @staticmethod
    def _sheet_matches_filter(row, field, mode, text):
        if not text:
            return True
        text = text.lower()
        if field == "Sheet Number":
            val = (row.Number or "").lower()
        elif field == "Sheet Name":
            val = (row.Name or "").lower()
        elif field == "Sheet Collection":
            val = (row.Collection or "").lower()
        else:   # "Number, Name, or Collection"
            val = ((row.Number or "") + " " + (row.Name or "") + " " + (row.Collection or "")).lower()

        if mode == "Contains":
            return text in val
        elif mode == "Does not contain":
            return text not in val
        elif mode == "Begins with":
            return val.startswith(text)
        elif mode == "Ends with":
            return val.endswith(text)
        elif mode == "Equals":
            return val == text
        return True

    def _on_sheet_filter_apply(self, sender, args):
        field = str(self.CboSheetFilterField.SelectedItem or "Sheet Number")
        mode  = str(self.CboSheetFilterMode.SelectedItem or "Contains")
        text  = (self.TxtSheetFilterValue.Text or "").strip()

        if not text:
            self.IcSheetGroups.ItemsSource = self.group_rows
        else:
            filtered = []
            for g in self.group_rows:
                matched = [s for s in g.Sheets
                           if self._sheet_matches_filter(s, field, mode, text)]
                if matched:
                    # Separate wrapper objects sharing the SAME underlying
                    # _SheetRow instances — checked-state stays in sync with
                    # the master group list automatically since they're the
                    # same objects, no copy of the checkbox state involved.
                    fg = _SheetGroupRow(g.Name, matched)
                    filtered.append(fg)
            self.IcSheetGroups.ItemsSource = filtered
        self._last_sheet_click = None
        self._refresh_sheet_tree()

    def _on_sheet_filter_clear(self, sender, args):
        self.TxtSheetFilterValue.Text = ""
        self.CboSheetFilterField.SelectedIndex = 0
        self.CboSheetFilterMode.SelectedIndex = 0
        self.IcSheetGroups.ItemsSource = self.group_rows
        self._last_sheet_click = None
        self._refresh_sheet_tree()

    # ------------------------------------------------------------------
    # Check All / Uncheck All / Toggle All / Expand All / Collapse All —
    # all operate on whatever is CURRENTLY displayed (respects an active
    # filter), matching how these buttons behave elsewhere in this wizard.
    # ------------------------------------------------------------------
    def _visible_sheet_groups(self):
        return self.IcSheetGroups.ItemsSource or self.group_rows

    def _set_all_sheets_checked(self, value):
        for g in self._visible_sheet_groups():
            for s in g.Sheets:
                s.IsChecked = value
        self._refresh_sheet_tree()

    def _toggle_all_sheets_checked(self):
        for g in self._visible_sheet_groups():
            for s in g.Sheets:
                s.IsChecked = not s.IsChecked
        self._refresh_sheet_tree()

    def _set_all_groups_expanded(self, value):
        for g in self.group_rows:
            g.IsExpanded = value
        visible = self.IcSheetGroups.ItemsSource
        if visible is not None and visible is not self.group_rows:
            for g in visible:
                g.IsExpanded = value
        self._refresh_sheet_tree()

    # ------------------------------------------------------------------
    # Group header checkbox (cascades to every sheet in that group) and
    # individual sheet checkbox (just recomputes counts) share one handler,
    # distinguished by the checked control's DataContext type.
    # ------------------------------------------------------------------
    # ------------------------------------------------------------------
    # Direct control manipulation for the sheet tree — bypasses WPF's
    # binding-refresh machinery entirely rather than depending on it. Two
    # prior attempts at "let the binding push the update" both proved unsafe
    # in this file: an INotifyPropertyChanged rewrite elsewhere (_SepRow)
    # broke rendering outright, and calling Items.Refresh() reactively from
    # within a Checked/Unchecked handler on the same control caused Revit to
    # freeze (container regeneration re-firing Checked events in a loop).
    # Directly finding and toggling the actual rendered CheckBox/TextBlock
    # controls avoids both hazards: one bounded, one-shot visual-tree walk
    # per action (scoped to a single group, not the whole tree), no retry
    # loop (the window is already fully rendered by the time a user can
    # click anything, unlike the __init__-time freeze from an earlier fix),
    # and no reliance on property-change notification at all.
    # ------------------------------------------------------------------
    @staticmethod
    def _find_descendant(parent, type_):
        try:
            count = VisualTreeHelper.GetChildrenCount(parent)
        except Exception:
            return None
        for i in range(count):
            try:
                child = VisualTreeHelper.GetChild(parent, i)
            except Exception:
                continue
            if isinstance(child, type_):
                return child
            found = ExportWizardWindow._find_descendant(child, type_)
            if found is not None:
                return found
        return None

    def _find_inner_sheets_control(self, group):
        """Locate the nested ItemsControl (bound to group.Sheets) inside the
        outer tree's container for `group`. One-shot — no Dispatcher retry."""
        try:
            self.IcSheetGroups.UpdateLayout()
            outer_container = self.IcSheetGroups.ItemContainerGenerator.ContainerFromItem(group)
            if outer_container is None:
                return None
            return self._find_descendant(outer_container, ItemsControl)
        except Exception:
            return None

    def _sync_group_header_visual(self, group):
        """Push group.HeaderText onto its actual rendered TextBlock (tagged
        Tag='hdrtext' in the XAML so it's found unambiguously among the
        header's other TextBlocks) — no binding refresh involved."""
        try:
            self.IcSheetGroups.UpdateLayout()
            outer_container = self.IcSheetGroups.ItemContainerGenerator.ContainerFromItem(group)
            if outer_container is None:
                return
            tb = self._find_tagged_textblock(outer_container, "hdrtext")
            if tb is not None:
                tb.Text = group.HeaderText
        except Exception:
            pass

    @staticmethod
    def _find_tagged_textblock(parent, tag_value):
        try:
            count = VisualTreeHelper.GetChildrenCount(parent)
        except Exception:
            return None
        for i in range(count):
            try:
                child = VisualTreeHelper.GetChild(parent, i)
            except Exception:
                continue
            if isinstance(child, TextBlock) and getattr(child, "Tag", None) == tag_value:
                return child
            found = ExportWizardWindow._find_tagged_textblock(child, tag_value)
            if found is not None:
                return found
        return None

    def _sync_sheets_visual(self, group, sheets):
        """After `sheets`' IsChecked values were changed in the data model
        (a group cascade or a shift+click range), push those values onto
        their ACTUAL rendered CheckBox controls directly so they visually
        update immediately — then refresh that one group's header text the
        same way. Bounded to a single group's sheet count, never the whole
        tree, and does not touch IcSheetGroups.Items at all."""
        inner = self._find_inner_sheets_control(group)
        if inner is not None:
            try:
                inner.UpdateLayout()
            except Exception:
                pass
            for sheet in sheets:
                try:
                    container = inner.ItemContainerGenerator.ContainerFromItem(sheet)
                    if container is None:
                        continue
                    cb = self._find_descendant(container, CheckBox)
                    if cb is not None and bool(cb.IsChecked) != bool(sheet.IsChecked):
                        cb.IsChecked = sheet.IsChecked
                except Exception:
                    continue
        self._sync_group_header_visual(group)

    def _on_sheet_tree_check_changed(self, sender, args):
        cb = args.OriginalSource
        ctx = getattr(cb, "DataContext", None)
        if isinstance(ctx, _SheetGroupRow):
            new_val = bool(ctx.IsChecked)
            for s in ctx.Sheets:
                s.IsChecked = new_val
            self._recompute_sheet_tree_data()
            # Directly sync each child checkbox's visual state — setting
            # cb.IsChecked here WILL raise its own Checked/Unchecked event,
            # bubbling back into this same handler with ctx as a _SheetRow
            # (not a _SheetGroupRow), which just falls through to the plain
            # count-label update below — bounded, not recursive.
            self._sync_sheets_visual(ctx, ctx.Sheets)
        else:
            self._recompute_sheet_tree_data()
        self._update_sheet_count_label()

    def _find_group_for_sheet(self, sheet_row):
        for g in self._visible_sheet_groups():
            if sheet_row in g.Sheets:
                return g
        return None

    def _on_sheet_tree_click(self, sender, args):
        src = args.OriginalSource

        if isinstance(src, Button):
            # Chevron button: a genuine Button.Click (not a CheckBox event),
            # so refreshing here is safe — matches the Check All/Expand All
            # precedent, not the risky reactive-Checked pattern above.
            ctx = getattr(src, "DataContext", None)
            if isinstance(ctx, _SheetGroupRow):
                ctx.IsExpanded = not ctx.IsExpanded
                self._refresh_sheet_tree()
            return

        if isinstance(src, CheckBox):
            ctx = getattr(src, "DataContext", None)
            if not isinstance(ctx, _SheetRow):
                return   # group header checkbox — handled by Checked/Unchecked above
            group = self._find_group_for_sheet(ctx)
            if group is None:
                return
            visible_sheets = list(group.Sheets)
            if ctx not in visible_sheets:
                return
            idx = visible_sheets.index(ctx)

            # Shift+click range-select, scoped to sheets WITHIN the same
            # collection group — a range spanning two different groups isn't
            # supported (there's no single flattened index across nested
            # ItemsControls to anchor it to), which matches how Revit's own
            # Project Browser range-select behaves within one grouping level.
            shift_held = bool(Keyboard.Modifiers & ModifierKeys.Shift)
            if (shift_held and self._last_sheet_click is not None
                    and self._last_sheet_click[0] is group
                    and 0 <= self._last_sheet_click[1] < len(visible_sheets)):
                lo, hi = sorted((self._last_sheet_click[1], idx))
                state = ctx.IsChecked
                affected = visible_sheets[lo:hi + 1]
                for s in affected:
                    s.IsChecked = state
                self._recompute_sheet_tree_data()
                self._sync_sheets_visual(group, affected)
                self._update_sheet_count_label()

            self._last_sheet_click = (group, idx)

    def _recompute_sheet_tree_data(self):
        """Data-only recompute of every group's header text/checked-state/
        chevron — both the master group_rows AND whatever's currently
        displayed (a filtered view uses separate _SheetGroupRow wrapper
        objects, so each needs its own header recomputed even though they
        share the underlying sheets). Safe to call from anywhere, including
        reactive CheckBox.Checked/Unchecked handlers, since it never touches
        the ItemsControl's visual tree."""
        def _recompute(g):
            total = len(g.Sheets)
            sel = sum(1 for s in g.Sheets if s.IsChecked)
            g.HeaderText = "{}  ({} sheet{}, {} selected)".format(
                g.Name, total, "" if total == 1 else "s", sel)
            g.IsChecked = (total > 0 and sel == total)
            g.Chevron = u"\u25BE" if g.IsExpanded else u"\u25B8"

        for g in self.group_rows:
            _recompute(g)
        visible = self.IcSheetGroups.ItemsSource
        if visible is not None and visible is not self.group_rows:
            for g in visible:
                _recompute(g)

    def _refresh_sheet_tree(self):
        """Full visual refresh: recompute + Items.Refresh() + count label.
        ONLY call this from a genuine Button.Click handler (Check All,
        Uncheck All, Toggle All, Expand All, Collapse All, Filter Apply/
        Clear, chevron toggle) — NEVER from a CheckBox.Checked/Unchecked
        handler reacting to IcSheetGroups' own checkbox events, or it can
        freeze Revit (see _on_sheet_tree_check_changed for why)."""
        self._recompute_sheet_tree_data()
        self.IcSheetGroups.Items.Refresh()
        self._update_sheet_count_label()

    def _update_sheet_count_label(self):
        n = len(self._get_checked_sheet_numbers())
        total = len(self.sheet_rows)
        self.TxtSheetCountSelected.Text = "{} of {} sheet(s) selected".format(n, total)

    def _get_checked_sheet_numbers(self):
        return [r.Number for r in self.sheet_rows if r.IsChecked]

    # ------------------------------------------------------------------
    # Step 1: Profile
    # ------------------------------------------------------------------
    def _populate_profile_step(self):
        self._refresh_profile_list()
        self.BtnUseProfile.Click    += self._on_use_profile
        self.BtnRenameProfile.Click += self._on_rename_profile
        self.BtnNewProfile.Click    += self._on_new_profile
        self.BtnDeleteProfile.Click += self._on_delete_profile
        self.BtnSaveProfile.Click   += self._on_save_profile
        self.TxtSearchProfile.TextChanged += self._on_search_profile
        self.LvProfiles.SelectionChanged += self._on_profile_selection_changed
        self.LvProfiles.MouseDoubleClick += self._on_profile_list_double_click
        # Editing starts closed: Use/Rename/New/Delete active, Save inert.
        self._set_profile_switch_actions_enabled(True)
        self._update_active_profile_label()

        # GridViewColumn doesn't support "*" star-sizing like DataGrid does,
        # so the Parameters (Filename) column stayed a fixed 500px and left
        # a growing gap on the right whenever the window was resized wider.
        # SizeChanged fires on every resize (and once at startup) — resize
        # the column to consume whatever width is left after Profile Name
        # and a small scrollbar allowance, so it always reaches the true
        # right edge.
        self.LvProfiles.SizeChanged += self._on_profile_list_size_changed

    def _on_profile_list_size_changed(self, sender, args):
        try:
            available = self.LvProfiles.ActualWidth - self.ColProfileName.Width - 25
            if available > 100:
                self.ColParamsFilename.Width = available
        except Exception:
            pass

    def _refresh_profile_list(self, select_name=None):
        available_names = set(self.param_names)
        self._sync_profile_mru()
        rows = []
        select_row = None
        for name in self._profile_mru:
            params = self._profile_params(name)
            seps = self._profile_separators(name, params)
            segments = self._build_param_segments(params, seps, available_names)
            row = _ProfileRow(name, self._param_str(params, seps), segments)
            rows.append(row)
            if name == (select_name or self.profile_name):
                select_row = row
        self._all_profile_rows = rows   # unfiltered master list, for search
        self._apply_profile_search_filter()
        if select_row is not None:
            self.LvProfiles.SelectedItem = select_row

    def _sync_profile_mru(self):
        """Keep _profile_mru consistent with all_profiles: drop names that no
        longer exist (deleted), append any that exist but aren't tracked yet
        (shouldn't normally happen, but stay safe)."""
        existing = set(self.all_profiles.keys())
        self._profile_mru = [n for n in self._profile_mru if n in existing]
        for n in self.all_profiles.keys():
            if n not in self._profile_mru:
                self._profile_mru.append(n)

    def _bump_profile_mru(self, name):
        """Move a profile to the front of the MRU order — call whenever a
        profile is saved, renamed, or newly created, so whatever was just
        touched is always at the top of the list instead of wherever it
        happens to sort alphabetically."""
        if name in self._profile_mru:
            self._profile_mru.remove(name)
        self._profile_mru.insert(0, name)

    def _on_search_profile(self, sender, args):
        self.TxtSearchProfileGhost.Visibility = (
            Visibility.Collapsed if (self.TxtSearchProfile.Text or "").strip()
            else Visibility.Visible)
        self._apply_profile_search_filter()

    def _apply_profile_search_filter(self):
        """Apply search filter to the profile list. When Edit Profile is open,
        only show the active profile (self.profile_name) regardless of search."""
        if self.edit_profile_open:
            # Show only the active profile
            filtered = [r for r in self._all_profile_rows if r.Name == self.profile_name]
        else:
            q = (self.TxtSearchProfile.Text or "").strip().lower()
            if not q:
                filtered = self._all_profile_rows
            else:
                filtered = [r for r in self._all_profile_rows
                            if q in r.Name.lower() or q in r.ParamString.lower()]
        self.LvProfiles.ItemsSource = filtered

    @staticmethod
    def _build_param_segments(params, seps, available_names):
        """Build the list of _ParamSegment for a profile's parameter list —
        each parameter name marked IsMissing if it no longer exists in the
        current model (renamed/deleted since the profile was saved), joined
        using THIS profile's own saved separators (seps), not a hardcoded
        character. "(none)" separators contribute no visible text, matching
        how the actual filename is built. Separator segments are flagged
        IsSeparator=True so the display template can render them as plain
        connectors rather than boxed parameter-name chips."""
        segments = []
        for i, p in enumerate(params):
            if i > 0:
                sep = seps[i - 1] if i - 1 < len(seps) else "-"
                sep_text = "" if sep == "(none)" else sep
                if sep_text:
                    segments.append(_ParamSegment(sep_text, is_separator=True))
            segments.append(_ParamSegment(p, is_missing=(p not in available_names)))
        if not segments:
            segments.append(_ParamSegment("(no parameters)"))
        return segments

    def _update_active_profile_label(self):
        badge = "  [LAST USED]" if (self._last_used_profile_name is not None
                                    and self.profile_name == self._last_used_profile_name) else ""
        self.TxtActiveProfile.Text = "Active profile: {}{}".format(self.profile_name, badge)

    @staticmethod
    def _param_str(params, seps):
        parts = []
        for i, p in enumerate(params):
            parts.append(p)
            if i < len(params) - 1:
                sep = seps[i] if i < len(seps) else "-"
                parts.append("" if sep == "(none)" else sep)
        return "".join(parts)

    def _profile_separators(self, name, params):
        """Return the saved separators list for a profile, aligned 1:1 with
        `params` (seps[i] is the separator placed AFTER params[i]). Legacy
        profiles saved before "separators" existed, or any length mismatch
        (e.g. profile edited outside this session), fall back to "-" for the
        missing entries rather than crashing the preview."""
        entry = self.all_profiles.get(name)
        seps = entry.get("separators") if isinstance(entry, dict) else None
        seps = list(seps) if seps else []
        if len(seps) < len(params):
            seps += ["-"] * (len(params) - len(seps))
        elif len(seps) > len(params):
            seps = seps[:len(params)]
        return seps

    def _profile_params(self, name):
        """all_profiles values can be either a plain list (legacy) or a dict
        with a 'params' key (current format) — handle both."""
        entry = self.all_profiles.get(name)
        if entry is None:
            return []
        if isinstance(entry, dict):
            return entry.get("params", [])
        return entry

    # -- Use Profile: load the selected row's params/order into the checklist
    def _on_use_profile(self, sender, args):
        row = self.LvProfiles.SelectedItem
        if row is None:
            MessageBox.Show("Select a profile in the list first.",
                             "No Profile Selected",
                             MessageBoxButton.OK, MessageBoxImage.Information)
            return
        self._load_profile_into_editor(row, warn_on_missing=True)
        # Move it to the top, same as Save/Rename/New — "Use Profile" is a
        # deliberate action on this profile, so it should surface to the top
        # and stay selected/highlighted as the current one in use, not sit
        # wherever it happened to be in the list before.
        self._bump_profile_mru(row.Name)
        self._refresh_profile_list(select_name=row.Name)

    def _on_profile_selection_changed(self, sender, args):
        # Selecting a row in the list previously only highlighted it — the
        # left/right panels (checklist + Filename Configuration) kept showing
        # whichever profile was active before, until the user separately
        # clicked "Use Profile". That gap was the actual cause of repeated
        # "wrong profile shows up in Edit Profile" reports: people clicked a
        # row, then Edit Profile, and got the OLD active profile (often
        # whichever one loaded first/alphabetically) instead of the one they
        # just clicked. Auto-loading on selection removes that extra required
        # step entirely — the panels now always match whatever's highlighted.
        # Skipped while actively editing (profile-switch actions are already
        # disabled then) and on empty selections (e.g. an active search
        # filter that currently matches nothing).
        if self.edit_profile_open:
            return
        row = self.LvProfiles.SelectedItem
        if row is None:
            return
        self._load_profile_into_editor(row, warn_on_missing=False)

    def _on_profile_list_double_click(self, sender, args):
        # Reuses the exact same path as clicking the Edit Profile button —
        # setting IsChecked fires _on_edit_profile_toggle, which already
        # force-syncs to whatever row is selected before opening (the same
        # fix that resolved "Edit Profile opens the wrong profile"). No
        # duplicate logic needed here.
        if self.edit_profile_open or self.LvProfiles.SelectedItem is None:
            return
        self.BtnEditProfile.IsChecked = True

    def _load_profile_into_editor(self, row, warn_on_missing):
        self.profile_name = row.Name
        params = self._profile_params(row.Name)

        # Warn up front if this profile references parameters that no
        # longer exist in the current model (renamed/deleted since the
        # profile was saved) — catching this here, at profile-load time,
        # is earlier and clearer than only discovering it later via the
        # per-sheet "missing fields" warnings in the export report. Only
        # shown for an explicit "Use Profile" click (warn_on_missing=True) —
        # showing it on every single row click while browsing the list would
        # be a naggy popup storm instead of a helpful one-time warning.
        available_names = set(self.param_names)
        missing = [p for p in params if p not in available_names]
        if missing and warn_on_missing:
            MessageBox.Show(
                "The profile \"{}\" references {} parameter(s) that don't "
                "exist in this model (possibly renamed or removed since the "
                "profile was saved):\n\n{}\n\n"
                "These will be skipped. You can still use the profile, or "
                "open Edit Profile to update it.".format(
                    row.Name, len(missing), "\n".join("  \u2022 " + m for m in missing)),
                "Profile Has Missing Parameters",
                MessageBoxButton.OK, MessageBoxImage.Warning)

        pre_set = set(params)
        for r in self.param_rows:
            r.IsChecked = r.Name in pre_set
        self.IcParameters.Items.Refresh()
        # Use the profile's OWN saved order directly (filtered to params that
        # still exist), rather than the generic append-preserving refresh —
        # that generic path only preserves membership, not a specific saved
        # arrangement, which would otherwise silently drop this profile's order.
        self._param_order = [p for p in params if p in available_names]
        # Seed with the profile's OWN saved separators (e.g. "_") so loading
        # a profile restores exactly what was saved, instead of silently
        # falling back to whatever separator happened to be showing from
        # whichever profile was active before this one.
        seps = self._profile_separators(row.Name, params)
        seed_map = dict(zip(params, seps))
        self._rebuild_sep_rows_from_order(seed_separators=seed_map)
        self._update_active_profile_label()
        # Refresh the profile list to show only the active one if editing is open
        if self.edit_profile_open:
            self._apply_profile_search_filter()

    # -- Save Profile: explicitly persist the current ticked/arranged state
    #    into the ACTIVE profile. This is now the ONLY way a profile's saved
    #    definition changes — replacing the old behavior where every single
    #    export silently overwrote whatever profile happened to be active
    #    with whatever was currently ticked, regardless of whether the user
    #    actually intended to change that profile. That silent overwrite was
    #    the root cause of profiles ending up with unexpected/mismatched
    #    parameter lists.
    def _on_save_profile(self, sender, args):
        # Read the grid EXACTLY as currently displayed — do NOT call
        # refresh_separators_from_step3() here. That rebuilds every _SepRow
        # from scratch (fresh objects) and re-applies the last-row-defaults-
        # to-none rule, which caused live edits to be silently overwritten at
        # save time. self.sep_rows is already kept in sync as-you-go (ticking
        # a parameter, reordering with the arrows), so it's already correct.
        params = [row.Name for row in self.sep_rows]
        if not params:
            MessageBox.Show(
                "Tick at least one parameter before saving this profile.",
                "Nothing to Save",
                MessageBoxButton.OK, MessageBoxImage.Warning)
            return

        separators = [row.Separator for row in self.sep_rows]

        # Nothing-changed check: compare against the snapshot taken the
        # moment Edit Profile was opened. If the parameter order and every
        # separator are identical, there's genuinely nothing to write —
        # say so instead of silently "saving" an unchanged profile.
        snapshot_order = getattr(self, "_edit_snapshot_order", None)
        snapshot_seps = getattr(self, "_edit_snapshot_seps", None)
        if snapshot_order is not None and snapshot_seps is not None:
            current_seps_by_name = dict(zip(params, separators))
            snapshot_seps_for_current_order = {
                n: snapshot_seps.get(n) for n in snapshot_order}
            if params == snapshot_order \
                    and current_seps_by_name == snapshot_seps_for_current_order:
                MessageBox.Show(
                    "Ano ba yan? Walang nabago!",
                    "Nothing to Save",
                    MessageBoxButton.OK, MessageBoxImage.Information)
                return

        self.all_profiles[self.profile_name] = {
            "params": params,
            "separators": separators,
            "order": list(range(1, len(params) + 1)),
        }
        self._bump_profile_mru(self.profile_name)
        self._refresh_profile_list(select_name=self.profile_name)

        # Auto-close Edit Profile after a successful save (this also
        # unfreezes Use/New/Delete Profile via the toggle-off handler below —
        # one consistent mechanism instead of two). This matters beyond just
        # convenience: if the fold-out stayed open and the user later
        # switched to a different profile then clicked "Edit Profile" again
        # (e.g. out of habit), that click would TURN IT OFF, since it was
        # already checked — making Filename Configuration vanish until
        # clicked a second time. Always starting closed after a save means
        # the next click on Edit Profile reliably opens it.
        self.BtnEditProfile.IsChecked = False

        MessageBox.Show(
            "Profile \"{}\" saved with {} parameter(s).".format(
                self.profile_name, len(params)),
            "Profile Saved",
            MessageBoxButton.OK, MessageBoxImage.Information)

    # -- Rename Profile: change the selected profile's name, keeping its
    #    params/separators/order exactly as they were.
    def _on_rename_profile(self, sender, args):
        row = self.LvProfiles.SelectedItem
        if row is None:
            MessageBox.Show("Select a profile in the list first.",
                             "No Profile Selected",
                             MessageBoxButton.OK, MessageBoxImage.Information)
            return
        old_name = row.Name
        dlg = InputDialog(self, "Rename Profile",
                          "Enter a new name for \"{}\":".format(old_name),
                          old_name)
        new_name = dlg.show()
        if not new_name or new_name == old_name:
            return   # cancelled, blank, or unchanged
        if new_name in self.all_profiles:
            MessageBox.Show(
                "A profile named \"{}\" already exists.".format(new_name),
                "Duplicate Profile",
                MessageBoxButton.OK, MessageBoxImage.Warning)
            return

        self.all_profiles[new_name] = self.all_profiles.pop(old_name)
        if old_name in self._profile_mru:
            self._profile_mru[self._profile_mru.index(old_name)] = new_name
        if self.profile_name == old_name:
            self.profile_name = new_name
        self._bump_profile_mru(new_name)
        self._refresh_profile_list(select_name=new_name)
        self._update_active_profile_label()

    # -- New Profile: ask for a name, add an empty profile, switch to it
    def _on_new_profile(self, sender, args):
        dlg = InputDialog(self, "New Profile",
                          "Enter a name for the new profile:", "")
        name = dlg.show()
        if not name:
            return   # cancelled or blank
        if name in self.all_profiles:
            MessageBox.Show(
                "A profile named \"{}\" already exists.".format(name),
                "Duplicate Profile",
                MessageBoxButton.OK, MessageBoxImage.Warning)
            return

        self.all_profiles[name] = {"params": [], "separators": [], "order": []}
        self.profile_name = name
        self._bump_profile_mru(name)
        self._refresh_profile_list(select_name=name)

        # Start the new profile empty so the user builds it from scratch.
        for r in self.param_rows:
            r.IsChecked = False
        self.IcParameters.Items.Refresh()
        self.refresh_separators_from_step3()
        self._update_active_profile_label()

        # Open the Edit Profile fold-out automatically so there's somewhere
        # to actually build the new (currently empty) profile.
        self.BtnEditProfile.IsChecked = True

    # -- Delete Profile: remove the selected row, guard against deleting the
    #    only remaining profile
    def _on_delete_profile(self, sender, args):
        row = self.LvProfiles.SelectedItem
        if row is None:
            MessageBox.Show("Select a profile in the list first.",
                             "No Profile Selected",
                             MessageBoxButton.OK, MessageBoxImage.Information)
            return
        if len(self.all_profiles) <= 1:
            MessageBox.Show("At least one profile must remain.",
                             "Cannot Delete",
                             MessageBoxButton.OK, MessageBoxImage.Warning)
            return

        answer = MessageBox.Show(
            "Delete profile \"{}\"? This cannot be undone.".format(row.Name),
            "Confirm Delete",
            MessageBoxButton.OKCancel, MessageBoxImage.Question)
        if answer != MessageBoxResult.OK:
            return

        deleted_was_active = (row.Name == self.profile_name)
        del self.all_profiles[row.Name]

        if deleted_was_active:
            fallback = "Default" if "Default" in self.all_profiles else sorted(self.all_profiles.keys())[0]
            self.profile_name = fallback
            params = self._profile_params(fallback)
            pre_set = set(params)
            for r in self.param_rows:
                r.IsChecked = r.Name in pre_set
            self.IcParameters.Items.Refresh()
            available_names = set(self.param_names)
            self._param_order = [p for p in params if p in available_names]
            seps = self._profile_separators(fallback, params)
            seed_map = dict(zip(params, seps))
            self._rebuild_sep_rows_from_order(seed_separators=seed_map)

        self._refresh_profile_list()
        self._update_active_profile_label()

    def _wire_edit_profile_toggle(self):
        """
        BtnEditProfile is a ToggleButton in window.xaml. Checked -> show the
        fold-out (Parameters + Separators side by side); unchecked -> collapse
        it back down. Folding it into Profile replaces the old standalone
        Parameters/Separators steps.
        """
        self.BtnEditProfile.Checked += self._on_edit_profile_toggle
        self.BtnEditProfile.Unchecked += self._on_edit_profile_toggle
        self.BtnCancelEditProfile.Click += self._on_cancel_edit_profile

    def _on_edit_profile_toggle(self, sender, args):
        self.edit_profile_open = bool(self.BtnEditProfile.IsChecked)

        # BUG FIX: clicking Edit Profile must always edit whichever profile
        # is actually highlighted in the list right now, not just whatever
        # self.profile_name happened to be left at. Previously, selecting a
        # profile row and immediately clicking Edit Profile could still open
        # editing against a stale, different profile if self.profile_name
        # hadn't been explicitly synced to that selection first.
        if self.edit_profile_open:
            selected_row = self.LvProfiles.SelectedItem
            if selected_row is not None and selected_row.Name != self.profile_name:
                self._load_profile_into_editor(selected_row, warn_on_missing=False)

        self.PanelEditProfile.Visibility = (
            Visibility.Visible if self.edit_profile_open else Visibility.Collapsed)
        # The fold-out's row is Auto while closed (claims zero space — no
        # dead gap below the profile list) and Star while open (stretches to
        # fill whatever height the window/card is resized to, so dragging
        # the window taller actually grows the Parameters/Filename
        # Configuration lists instead of leaving blank space below them).
        # RowProfileList does the inverse: Star while closed (the profile
        # list itself fills all available height instead of being capped),
        # Auto while open (shrinks back to its natural content size so the
        # fold-out gets the room).
        self.RowEditProfile.Height = (
            GridLength(1, GridUnitType.Star) if self.edit_profile_open
            else GridLength(0, GridUnitType.Auto))
        self.RowProfileList.Height = (
            GridLength(0, GridUnitType.Auto) if self.edit_profile_open
            else GridLength(1, GridUnitType.Star))
        # Freeze profile-switching actions while actively editing. Without
        # this, clicking a different row in the profile list (without first
        # clicking "Use Profile" on it) did nothing to self.profile_name —
        # so ticking/saving would silently continue targeting the ORIGINAL
        # profile while the list visually showed a different row selected.
        # That mismatch was the actual cause of editing appearing "stuck":
        # the active profile never actually changed, so nothing else seemed
        # editable. Requiring Edit Profile to be closed before switching
        # eliminates that ambiguous state entirely.
        self._set_profile_switch_actions_enabled(not self.edit_profile_open)
        self.TxtEditingHint.Visibility = (
            Visibility.Visible if self.edit_profile_open else Visibility.Collapsed)

        # Link (or unlink) the inline editor to the row for self.profile_name.
        # IsEditing/EditRows drive the DataTrigger in the Parameters (Filename)
        # column that swaps the read-only chip display for the live editable
        # one. Every OTHER row's IsEditing stays False, so only one profile's
        # row ever shows the editor at a time.
        for row in getattr(self, "_all_profile_rows", []):
            row.IsEditing = self.edit_profile_open and row.Name == self.profile_name
            row.EditRows = self.sep_rows if row.IsEditing else None
        try:
            self.LvProfiles.Items.Refresh()
        except Exception:
            pass

        if self.edit_profile_open:
            # Make sure the separator rows reflect whatever is currently ticked
            self.refresh_separators_from_step3()
            # Snapshot for Cancel: exact ticked-parameter set (by name) and
            # each row's separator, captured at the moment editing opens —
            # not the saved profile on disk, since re-opening Edit Profile
            # without saving in between should still let you cancel back to
            # THIS session's starting point.
            self._edit_snapshot_checked = set(
                r.Name for r in self.param_rows if r.IsChecked)
            self._edit_snapshot_order = list(self._param_order)
            self._edit_snapshot_seps = {
                row.Name: row.Separator for row in self.sep_rows}
            # Refresh profile list to hide others
            self._apply_profile_search_filter()
        else:
            # Editing closed – show all profiles again (respecting search)
            self._apply_profile_search_filter()

    def _on_cancel_edit_profile(self, sender, args):
        snapshot_checked = getattr(self, "_edit_snapshot_checked", None)
        snapshot_order = getattr(self, "_edit_snapshot_order", None)
        snapshot_seps = getattr(self, "_edit_snapshot_seps", None)
        if snapshot_checked is not None:
            for r in self.param_rows:
                r.IsChecked = r.Name in snapshot_checked
            self.IcParameters.Items.Refresh()
            self._param_order = list(snapshot_order) if snapshot_order else []
            seed_map = dict(snapshot_seps) if snapshot_seps else None
            self._rebuild_sep_rows_from_order(seed_separators=seed_map)
        # Close the fold-out without saving — unchecking triggers
        # _on_edit_profile_toggle's normal "closed" path (row-height
        # toggle, re-enabling Use/Rename/New/Delete, hiding the hint).
        self.BtnEditProfile.IsChecked = False

    def _set_profile_switch_actions_enabled(self, enabled):
        # Use/Rename/New/Delete are only meaningful when NOT actively editing
        # (switching profiles mid-edit was the original source of the
        # "editing looks stuck" bug). Save Profile is the exact opposite —
        # it only does something once Edit Profile has actually been opened,
        # so it stays disabled otherwise rather than sitting there invitingly
        # clickable with nothing to save.
        #
        # LvProfiles itself is deliberately NOT frozen here — it should stay
        # scrollable/browsable at all times so you can still look at other
        # profiles' parameter combos while editing one. Actually switching
        # the active profile mid-edit is already independently blocked in
        # _on_profile_selection_changed (checks self.edit_profile_open), so
        # disabling the whole control here would only have blocked harmless
        # browsing, not anything unsafe.
        self.BtnUseProfile.IsEnabled = enabled
        self.BtnRenameProfile.IsEnabled = enabled
        self.BtnNewProfile.IsEnabled = enabled
        self.BtnDeleteProfile.IsEnabled = enabled
        self.BtnSaveProfile.IsEnabled = not enabled

    # ------------------------------------------------------------------
    # Edit Profile fold-out - Parameters (left half)
    # ------------------------------------------------------------------
    # Row-height constants for computing a precise ScrollViewer height that
    # always snaps to a whole number of rows — avoids the DataGrid/ItemsControl
    # rendering a partial row cut off mid-height when MaxHeight alone doesn't
    # divide evenly into the actual row size.
    _PARAM_ROW_HEIGHT = 24
    _PARAM_MAX_VISIBLE_ROWS = 10

    def _populate_parameters_step(self, preselected):
        pre_set = set(preselected)
        self.param_rows = [_ParamRow(p, p in pre_set) for p in self.param_names]
        self.IcParameters.ItemsSource = self.param_rows
        self._update_param_scrollviewer_height(len(self.param_rows))
        self.TxtSearchParam.TextChanged += self._on_search_param
        self.BtnCheckAll.Click   += lambda s, e: self._set_all_checked(True)
        self.BtnUncheckAll.Click += lambda s, e: self._set_all_checked(False)
        self.BtnToggleAll.Click  += lambda s, e: self._toggle_all_checked()
        # Shift+click range select — same pattern as the sheet checklist
        # (see _on_sheet_tree_click): Click is a bubbling ButtonBase
        # event (CheckBox derives from ToggleButton -> ButtonBase), so one
        # handler on the parent ItemsControl catches every row's click.
        self._last_param_click_index = None
        self.IcParameters.AddHandler(
            ButtonBase.ClickEvent, RoutedEventHandler(self._on_param_checkbox_click))

    def _on_param_checkbox_click(self, sender, args):
        """Range-select support: Shift+click a parameter to set every row
        between it and the last-clicked row to the same checked state — in
        the DIRECTION clicked. A top-to-bottom drag (anchor above the new
        click) orders the range ascending (matches visual top-to-bottom); a
        bottom-to-top drag (anchor below) orders it descending. This is
        handled explicitly here rather than deferring to
        refresh_separators_from_step3()'s generic append, which always uses
        the master list's fixed order and would ignore drag direction
        entirely (e.g. scrambling a bottom-to-top selection)."""
        cb = args.OriginalSource
        row = getattr(cb, "DataContext", None)
        if row is None or row not in getattr(self, "param_rows", []):
            return
        visible = list(self.IcParameters.ItemsSource)
        if row not in visible:
            self._last_param_click_index = None
            return
        idx = visible.index(row)

        shift_held = bool(Keyboard.Modifiers & ModifierKeys.Shift)
        if shift_held and self._last_param_click_index is not None \
                and 0 <= self._last_param_click_index < len(visible):
            anchor = self._last_param_click_index
            state = row.IsChecked
            if idx >= anchor:
                ordered_range = visible[anchor:idx + 1]                  # top -> bottom
            else:
                ordered_range = list(reversed(visible[idx:anchor + 1]))  # bottom -> top

            for r in ordered_range:
                r.IsChecked = state
            self.IcParameters.Items.Refresh()

            # Update _param_order directly in click direction for this range,
            # instead of the generic refresh (master-list-order append).
            range_names = [r.Name for r in ordered_range]
            if state:
                # Newly checked: drop any prior occurrence (shouldn't be one,
                # but stay safe against re-selecting an overlapping range),
                # then append the whole range in the exact direction clicked
                # — consistent with how a single new tick always appends.
                keep = set(range_names)
                self._param_order = [n for n in self._param_order if n not in keep]
                self._param_order.extend(range_names)
            else:
                drop = set(range_names)
                self._param_order = [n for n in self._param_order if n not in drop]
            self._rebuild_sep_rows_from_order()

        self._last_param_click_index = idx

    def _update_param_scrollviewer_height(self, visible_count):
        # MinHeight only — a floor so a short list doesn't collapse to
        # near-nothing, while VerticalAlignment=Stretch + the parent Grid's
        # star row still let it grow to fill whatever space is available
        # when the window/card is resized taller.
        rows = max(1, min(visible_count, self._PARAM_MAX_VISIBLE_ROWS))
        self.SvParameters.MinHeight = rows * self._PARAM_ROW_HEIGHT

    def _on_search_param(self, sender, args):
        q = sender.Text.strip().lower()
        # Simple filter: rebind a filtered view; IronPython/WPF ItemsControl
        # doesn't need a CollectionView for this scale, so just re-set ItemsSource.
        if not q:
            filtered = self.param_rows
        else:
            filtered = [r for r in self.param_rows if q in r.Name.lower()]
        self.IcParameters.ItemsSource = filtered
        self._update_param_scrollviewer_height(len(filtered))
        self._last_param_click_index = None

    def _set_all_checked(self, value):
        for r in self.param_rows:
            r.IsChecked = value
        self.IcParameters.Items.Refresh()

    def _toggle_all_checked(self):
        for r in self.param_rows:
            r.IsChecked = not r.IsChecked
        self.IcParameters.Items.Refresh()

    def _get_checked_params_in_order(self):
        return [r.Name for r in self.param_rows if r.IsChecked]

    # ------------------------------------------------------------------
    # Edit Profile fold-out - inline chip editor (lives in the profile
    # list's "Parameters (Filename)" column, not a separate grid)
    # ------------------------------------------------------------------
    def _populate_separators_step(self):
        self._param_order = list(self._get_checked_params_in_order())
        # Seed from the active profile's OWN saved separators. Without this,
        # the very first build of self.sep_rows has no prior in-session state
        # to fall back to (getattr(self, "sep_rows", []) is empty), so every
        # row silently defaulted to "-" regardless of what was actually saved
        # — the main source of "I set underscore, saved, reopened, and it's
        # back to hyphen".
        saved_params = self._profile_params(self.profile_name)
        saved_seps = self._profile_separators(self.profile_name, saved_params)
        seed_map = dict(zip(saved_params, saved_seps))
        self._rebuild_sep_rows_from_order(seed_separators=seed_map)

        # Live sync: CheckBox.Checked/Unchecked are routed events that bubble
        # up through the visual tree, so a single handler on the parent
        # ItemsControl catches every tick/untick inside it — no per-row
        # wiring and no manual "Refresh" button needed. Separators rebuild
        # immediately whenever the ticked-parameter set changes.
        self.IcParameters.AddHandler(
            CheckBox.CheckedEvent, RoutedEventHandler(self._on_param_check_changed))
        self.IcParameters.AddHandler(
            CheckBox.UncheckedEvent, RoutedEventHandler(self._on_param_check_changed))

        # The Separator field is a plain TextBox (no preset dropdown). Bound
        # Text OneWay only, same reasoning as everywhere else in this file:
        # TwoWay binding write-back onto a plain _SepRow object isn't
        # reliable in this IronPython/WPF setup, so the actual write happens
        # explicitly here, driven by the bubbling TextChanged event instead.
        # Wired on LvProfiles (not a per-row element) since the editable
        # chips live inside the profile list's own DataTemplate now.
        self.LvProfiles.AddHandler(
            TextBox.TextChangedEvent, TextChangedEventHandler(self._on_sep_text_changed))

        # Drag-to-reorder: click-and-drag a chip (anywhere except its
        # Separator textbox, which keeps normal click/type behavior) to drop
        # it at a new position. Threshold-based (SystemParameters.Minimum*
        # DragDistance) so a plain click never triggers a drag — only an
        # actual drag gesture does. Same proven pattern as the old DataGrid
        # version, just retargeted at Border elements (Tag="EditChip")
        # instead of DataGridRow.
        self._sep_drag_row = None
        self._sep_drag_start = None
        self.LvProfiles.AllowDrop = True
        self.LvProfiles.AddHandler(
            UIElement.PreviewMouseLeftButtonDownEvent,
            MouseButtonEventHandler(self._on_sep_row_preview_mouse_down), True)
        self.LvProfiles.AddHandler(
            UIElement.PreviewMouseMoveEvent,
            MouseEventHandler(self._on_sep_row_preview_mouse_move), True)
        self.LvProfiles.AddHandler(
            UIElement.DropEvent, DragEventHandler(self._on_sep_row_drop), True)
        self.LvProfiles.AddHandler(
            UIElement.GiveFeedbackEvent, GiveFeedbackEventHandler(self._on_sep_row_give_feedback), True)
        self.LvProfiles.AddHandler(
            UIElement.PreviewDragOverEvent, DragEventHandler(self._on_sep_row_drag_over), True)
        self.LvProfiles.AddHandler(
            UIElement.DragLeaveEvent, DragEventHandler(self._on_sep_row_drag_leave), True)
        self._sep_drop_target_row = None

    def _find_edit_chip(self, dep_obj):
        """Walk up from dep_obj to the nearest Border tagged 'EditChip' (the
        draggable parameter chip in the inline editor). Returns that Border,
        or None if dep_obj isn't inside one."""
        while dep_obj is not None:
            if isinstance(dep_obj, Border) and getattr(dep_obj, "Tag", None) == "EditChip":
                return dep_obj
            try:
                dep_obj = VisualTreeHelper.GetParent(dep_obj)
            except Exception:
                return None
        return None

    def _is_interactive_control(self, dep_obj, stop_type=None):
        """True if dep_obj sits inside a TextBox or any ButtonBase before
        reaching an EditChip border (or running out of ancestors) — those
        keep their normal click/type behavior and never start a drag."""
        while dep_obj is not None:
            if isinstance(dep_obj, (TextBox, ButtonBase)):
                return True
            if isinstance(dep_obj, Border) and getattr(dep_obj, "Tag", None) == "EditChip":
                return False
            try:
                dep_obj = VisualTreeHelper.GetParent(dep_obj)
            except Exception:
                break
        return False

    def _on_sep_row_preview_mouse_down(self, sender, args):
        source = args.OriginalSource
        if self._is_interactive_control(source):
            self._sep_drag_row = None
            self._sep_drag_start = None
            return
        chip = self._find_edit_chip(source)
        if chip is None:
            self._sep_drag_row = None
            self._sep_drag_start = None
            return
        self._sep_drag_row = chip.DataContext
        self._sep_drag_start = args.GetPosition(None)

    def _on_sep_row_preview_mouse_move(self, sender, args):
        if self._sep_drag_row is None or self._sep_drag_start is None:
            return
        if args.LeftButton != MouseButtonState.Pressed:
            return
        pos = args.GetPosition(None)
        dx = abs(pos.X - self._sep_drag_start.X)
        dy = abs(pos.Y - self._sep_drag_start.Y)
        if dx < SystemParameters.MinimumHorizontalDragDistance \
                and dy < SystemParameters.MinimumVerticalDragDistance:
            return
        dragged = self._sep_drag_row
        self._sep_drag_row = None
        self._sep_drag_start = None
        try:
            self.DragGhostText.Text = dragged.Label
            cursor_pt = WinForms.Cursor.Position
            self.DragGhostPopup.HorizontalOffset = cursor_pt.X + 14
            self.DragGhostPopup.VerticalOffset = cursor_pt.Y + 14
            self.DragGhostPopup.IsOpen = True
        except Exception:
            pass
        try:
            data = DataObject("KzkSepRowDrag", dragged)
            DragDrop.DoDragDrop(self.LvProfiles, data, DragDropEffects.Move)
        except Exception:
            pass
        finally:
            self.DragGhostPopup.IsOpen = False
            self._clear_sep_drop_target()

    def _clear_sep_drop_target(self):
        # Direct local-value manipulation on the actual chip Border visual —
        # deliberately NOT going through data binding + Items.Refresh() DURING
        # the drag. That approach (tried on the old DataGrid version) forced
        # container regeneration on every hover change while a drag was still
        # active, and that regeneration race is exactly what left the
        # dropped-on row as WPF's {DisconnectedItem} sentinel right as Drop
        # fired. Refresh() is only called from _on_sep_row_drop, AFTER the
        # drag has fully ended, which is not subject to that race.
        if self._sep_drop_target_row is not None:
            try:
                self._sep_drop_target_row.ClearValue(Border.BackgroundProperty)
                self._sep_drop_target_row.ClearValue(Border.BorderBrushProperty)
                self._sep_drop_target_row.ClearValue(Border.BorderThicknessProperty)
            except Exception:
                pass
            self._sep_drop_target_row = None

    def _on_sep_row_give_feedback(self, sender, args):
        # Fires continuously while the drag is active — reposition the ghost
        # box to track the live cursor (WinForms.Cursor.Position is in screen
        # coordinates, which is what Popup.HorizontalOffset/VerticalOffset
        # expect for Placement="Absolute").
        try:
            cursor_pt = WinForms.Cursor.Position
            self.DragGhostPopup.HorizontalOffset = cursor_pt.X + 14
            self.DragGhostPopup.VerticalOffset = cursor_pt.Y + 14
        except Exception:
            pass
        args.UseDefaultCursors = True
        args.Handled = True

    def _on_sep_row_drag_over(self, sender, args):
        chip = self._find_edit_chip(args.OriginalSource)
        if chip is self._sep_drop_target_row:
            return
        self._clear_sep_drop_target()
        if chip is not None:
            try:
                chip.Background = _DROP_HIGHLIGHT_BG
                chip.BorderBrush = _DROP_HIGHLIGHT_BORDER
                chip.BorderThickness = Thickness(2)
                self._sep_drop_target_row = chip
            except Exception:
                pass

    def _on_sep_row_drag_leave(self, sender, args):
        self._clear_sep_drop_target()

    def _on_sep_row_drop(self, sender, args):
        self._clear_sep_drop_target()
        try:
            if not args.Data.GetDataPresent("KzkSepRowDrag"):
                return
            dragged = args.Data.GetData("KzkSepRowDrag")
        except Exception:
            return
        target_chip = self._find_edit_chip(args.OriginalSource)
        if target_chip is None:
            return
        target_item = target_chip.DataContext
        if target_item is dragged or dragged not in self.sep_rows \
                or target_item not in self.sep_rows:
            return
        old_idx = self.sep_rows.index(dragged)
        new_idx = self.sep_rows.index(target_item)
        previous_last_row = self.sep_rows[-1] if self.sep_rows else None
        self.sep_rows.pop(old_idx)
        self.sep_rows.insert(new_idx, dragged)
        # A manual reorder IS the new authoritative order — persist it so
        # ticking/unticking other parameters later doesn't discard it.
        self._param_order = [r.Name for r in self.sep_rows]
        self._apply_last_row_none_default(previous_last_row)
        self._renumber_sep_labels()
        self._relink_edit_rows()

    def _on_sep_text_changed(self, sender, args):
        tb = args.OriginalSource
        row = getattr(tb, "DataContext", None)
        if row is None or row not in self.sep_rows:
            return
        row.Separator = tb.Text

    def _on_param_check_changed(self, sender, args):
        self.refresh_separators_from_step3()

    def refresh_separators_from_step3(self):
        """Call whenever the ticked-parameter SET may have changed (navigating
        away from the Profile step, or a tick/untick). Preserves the existing
        manually-arranged order for anything still checked; removes anything
        unticked; appends newly-ticked parameters at the end. Never reorders
        parameters that were already arranged — only ticking/unticking
        changes membership, not position."""
        checked_set = set(self._get_checked_params_in_order())
        self._param_order = [n for n in self._param_order if n in checked_set]
        for name in self._get_checked_params_in_order():
            if name not in self._param_order:
                self._param_order.append(name)
        self._rebuild_sep_rows_from_order()

    def _rebuild_sep_rows_from_order(self, seed_separators=None):
        """(Re)build self.sep_rows from self._param_order.

        Each row's separator resolves in priority order:
          1. `seed_separators[name]` — a freshly-loaded profile's OWN saved
             separator, when one is supplied (Use Profile / delete-fallback).
             This must win over the in-session value, otherwise switching
             profiles (or restarting the tool) silently discarded the saved
             separator and replaced it with whatever the previous profile
             happened to have — the underscore-reverts-to-hyphen bug.
          2. the row's current in-session separator (old_by_name) — normal
             tick/untick/reorder within the same profile, no profile load.
          3. the default separator, for a name seen for the first time.

        Then renumber labels and update which row is forced to "(none)"
        (see _apply_last_row_none_default)."""
        old_rows = getattr(self, "sep_rows", [])
        previous_last_name = old_rows[-1].Name if old_rows else None
        old_by_name = {row.Name: row.Separator for row in old_rows}
        default_sep = self.sep_options[0] if self.sep_options else "-"

        def _resolve(name):
            if seed_separators is not None and name in seed_separators:
                return seed_separators[name]
            return old_by_name.get(name, default_sep)

        self.sep_rows = [
            _SepRow(name, self.sep_options, _resolve(name))
            for name in self._param_order
        ]
        # Rows are fresh objects here (not the same instances as old_rows),
        # so find the new object matching the previous last row's name, if
        # it's still present, to hand to _apply_last_row_none_default.
        previous_last_row = None
        if previous_last_name is not None:
            for r in self.sep_rows:
                if r.Name == previous_last_name:
                    previous_last_row = r
                    break
        self._apply_last_row_none_default(previous_last_row)
        self._renumber_sep_labels()
        self._relink_edit_rows()

    def _relink_edit_rows(self):
        """self.sep_rows gets reassigned to a brand-new list object on every
        rebuild (tick/untick, Cancel, profile load) — so whichever
        _ProfileRow currently has IsEditing=True needs its EditRows pointer
        refreshed to the new list every time, or the inline editor would
        keep showing a stale, disconnected copy. Cheap no-op when nothing
        is being edited."""
        for row in getattr(self, "_all_profile_rows", []):
            if getattr(row, "IsEditing", False):
                row.EditRows = self.sep_rows
        try:
            self.LvProfiles.Items.Refresh()
        except Exception:
            pass

    def _apply_last_row_none_default(self, previous_last_row=None):
        """Force whichever row is now last to "(none)" — a trailing
        separator before the extension doesn't make sense. If a DIFFERENT
        row was last before this call (previous_last_row) and it's still
        showing "(none)", reset it back to a normal default: otherwise a
        parameter that WAS last (and got auto-defaulted to none) would stay
        stuck at "(none)" forever after it's no longer last, while the row
        that's now last ALSO becomes "(none)" — accumulating multiple
        "none" rows over successive reorders/tick changes instead of just
        the one that's actually last right now."""
        if not self.sep_rows:
            return
        new_last = self.sep_rows[-1]
        if (previous_last_row is not None
                and previous_last_row is not new_last
                and previous_last_row.Separator == "(none)"):
            previous_last_row.Separator = self.sep_options[0] if self.sep_options else "-"
        if "(none)" in self.sep_options:
            new_last.Separator = "(none)"

    def _renumber_sep_labels(self):
        n = len(self.sep_rows)
        for i, row in enumerate(self.sep_rows):
            row.Label = "{}. {}".format(i + 1, row.Name)
            row.OrderNum = str(i + 1)
            row.IsLastRow = (i == n - 1)

    # ------------------------------------------------------------------
    # Step 2: Export Settings
    # ------------------------------------------------------------------
    def _populate_export_settings_step(self, format_opts, pdf_quality_opts,
                                        pdf_processing_opts, dwg_version_opts, folder_opts,
                                        dwfx_quality_opts, dwf_quality_opts, default_formats):
        # ── Output Format checklist ────────────────────────────────────
        self.format_rows = [_FormatRow(name, name in default_formats)
                             for name in format_opts]
        self.IcFormats.ItemsSource = self.format_rows
        self.BtnCheckAllFormats.Click   += lambda s, e: self._set_all_formats_checked(True)
        self.BtnUncheckAllFormats.Click += lambda s, e: self._set_all_formats_checked(False)
        self._wire_format_checkboxes()
        self._refresh_format_dependent_sections()

        self.CboDwfxQuality.ItemsSource   = dwfx_quality_opts
        self.CboDwfxQuality.SelectedIndex = 0

        self.CboDwfQuality.ItemsSource   = dwf_quality_opts
        self.CboDwfQuality.SelectedIndex = 0

        self.CboPdfQuality.ItemsSource     = pdf_quality_opts
        # Default to "Medium (150 DPI)" rather than the first entry (Low).
        # Falls back to index 0 if the option list doesn't contain it.
        try:
            self.CboPdfQuality.SelectedIndex = pdf_quality_opts.index("Medium (150 DPI)")
        except ValueError:
            self.CboPdfQuality.SelectedIndex = 0
        self.CboPdfProcessing.ItemsSource  = pdf_processing_opts
        self.CboPdfProcessing.SelectedIndex = 0
        self.CboDwgVersion.ItemsSource     = dwg_version_opts
        self.CboDwgVersion.SelectedIndex   = 0

        self.ChkHideCrop.IsChecked      = True
        self.ChkHideRef.IsChecked       = True
        self.ChkHideScope.IsChecked     = True
        self.ChkHideViewTags.IsChecked  = True

        if folder_opts:
            self.CboFolderMode.ItemsSource   = folder_opts
            self.CboFolderMode.SelectedIndex = 0
            self.CboFolderMode.Visibility = Visibility.Visible
            self.TxtFolderStructureLabel.Visibility = Visibility.Visible

        # Dark grey by default, red the instant the user picks anything
        # other than each combo's own default value — wired individually
        # (each closure captures its own combo + default) rather than one
        # shared handler, since the "default value" differs per control.
        self._wire_combo_toggle(self.CboDwfxQuality, str(self.CboDwfxQuality.SelectedItem))
        self._wire_combo_toggle(self.CboDwfQuality, str(self.CboDwfQuality.SelectedItem))
        self._wire_combo_toggle(self.CboPdfQuality, str(self.CboPdfQuality.SelectedItem))
        self._wire_combo_toggle(self.CboPdfProcessing, str(self.CboPdfProcessing.SelectedItem))
        self._wire_combo_toggle(self.CboDwgVersion, str(self.CboDwgVersion.SelectedItem))
        if folder_opts:
            self._wire_combo_toggle(self.CboFolderMode, str(self.CboFolderMode.SelectedItem))

    def _wire_combo_toggle(self, combo, default_value):
        combo.Background = _COMBO_DEFAULT_BG

        def _on_change(sender, args):
            try:
                current = str(combo.SelectedItem)
            except Exception:
                return
            combo.Background = (
                _COMBO_DEFAULT_BG if current == default_value else _COMBO_CHANGED_BG)

        combo.SelectionChanged += _on_change

    # ------------------------------------------------------------------
    # Output Format checklist (replaces old single-select CboExportFormat)
    # ------------------------------------------------------------------
    def _wire_format_checkboxes(self):
        """Hook Checked/Unchecked on the Output Format checklist so ticking any
        format re-evaluates which dependent sections (DWG/DXF/DWFx Version,
        PDF Settings) are enabled. Uses the same bubbling-event AddHandler
        pattern as IcSheetGroups/IcParameters — CheckBox.Checked/Unchecked bubble
        up to the containing ItemsControl regardless of when WPF generates
        the item containers, so no VisualTreeHelper walk or Dispatcher retry
        is needed (a prior version of this used exactly that and could
        livelock the UI thread if containers weren't generated yet)."""
        self.IcFormats.AddHandler(
            CheckBox.CheckedEvent, RoutedEventHandler(self._on_format_check_changed))
        self.IcFormats.AddHandler(
            CheckBox.UncheckedEvent, RoutedEventHandler(self._on_format_check_changed))

    def _on_format_check_changed(self, sender, args):
        self._refresh_format_dependent_sections()

    def _set_all_formats_checked(self, value):
        for r in self.format_rows:
            r.IsChecked = value
        self.IcFormats.Items.Refresh()
        self._refresh_format_dependent_sections()

    def _get_checked_format_names(self):
        return [r.Name for r in self.format_rows if r.IsChecked]

    def _refresh_format_dependent_sections(self):
        """Enable/dim the DWG/DXF/DWFx Version combo, DWFx Settings combo,
        and PDF Settings combos based on which formats are currently ticked.
        Disabled (not hidden) so the section stays visible for context."""
        checked = self._get_checked_format_names()
        needs_version = any(f in checked for f in ("DWG", "DXF"))
        needs_pdf     = any(f in checked for f in ("PDF", "PDF Merge"))
        needs_dwfx    = any(f in checked for f in ("DWFx", "DWFx Merge"))
        needs_dwf     = any(f in checked for f in ("DWF", "DWF Merge"))

        self.CboDwgVersion.IsEnabled = needs_version
        self.CboDwfxQuality.IsEnabled = needs_dwfx
        self.CboDwfQuality.IsEnabled  = needs_dwf
        self.CboPdfQuality.IsEnabled    = needs_pdf
        self.CboPdfProcessing.IsEnabled = needs_pdf
        self.ChkCompressPdf.IsEnabled   = needs_pdf
        self.ChkHideCrop.IsEnabled      = needs_pdf
        self.ChkHideRef.IsEnabled       = needs_pdf
        self.ChkHideScope.IsEnabled     = needs_pdf
        self.ChkHideViewTags.IsEnabled  = needs_pdf

    # ------------------------------------------------------------------
    # Pre-Export Actions: Sync with Central + Reload Links (both default OFF)
    # ------------------------------------------------------------------
    def _populate_pre_export_actions(self, link_options, is_workshared):
        # Sync with Central only makes sense on a workshared/central model —
        # hide the option entirely rather than show a checkbox that would
        # always be a no-op.
        if not is_workshared:
            self.ChkSyncCentral.Visibility = Visibility.Collapsed
            self.TxtSyncHint.Visibility = Visibility.Collapsed
        self.ChkSyncCentral.IsChecked = False   # default OFF

        # If link_options were provided directly, use them. Otherwise,
        # populate later via lazy link_provider on first checkbox tick.
        if link_options:
            self.link_rows = [_LinkRow(l["name"], l["path_display"], False) for l in link_options]
            self._links_loaded = True
        else:
            self.link_rows = []
        self.IcLinks.ItemsSource = self.link_rows

        self.ChkReloadLinks.IsChecked = False   # default OFF
        self.ChkReloadLinks.Checked   += self._on_reload_links_toggled
        self.ChkReloadLinks.Unchecked += self._on_reload_links_toggled
        self.BtnCheckAllLinks.Click   += lambda s, e: self._set_all_links_checked(True)
        self.BtnUncheckAllLinks.Click += lambda s, e: self._set_all_links_checked(False)

        if not link_options and not self._has_links:
            # No links in the model at all — nothing to reload, so hide the
            # whole control rather than show an empty checklist.
            self.ChkReloadLinks.Visibility = Visibility.Collapsed

    def _on_reload_links_toggled(self, sender, args):
        # Lazy-load link list the first time the user ticks "Reload Links".
        # This keeps the (potentially slow) full link scan off the dialog-open
        # path — it only runs once, when the user actually needs it.
        if self.ChkReloadLinks.IsChecked and not self._links_loaded:
            if self._link_provider is not None:
                try:
                    link_data = self._link_provider()
                    self.link_rows = [_LinkRow(l["name"], l["path_display"], False)
                                      for l in link_data]
                    self.IcLinks.ItemsSource = self.link_rows
                except Exception:
                    self.link_rows = []
            self._links_loaded = True
        self.PanelReloadLinks.Visibility = (
            Visibility.Visible if self.ChkReloadLinks.IsChecked else Visibility.Collapsed)

    def _set_all_links_checked(self, value):
        for r in self.link_rows:
            r.IsChecked = value
        self.IcLinks.Items.Refresh()

    def _get_checked_link_names(self):
        return [r.Name for r in self.link_rows if r.IsChecked]

    # ------------------------------------------------------------------
    # Finish
    # ------------------------------------------------------------------
    def _parse_schedule_datetime(self):
        """Combine the picked date (schedule_settings["date"]) with the typed HH:mm text
        into a single System.DateTime. Returns None if either is missing or
        the time text doesn't parse."""
        sched = self.schedule_settings
        d = sched.get("date")
        t = (sched.get("time") or "").strip()
        if d is None or not t:
            return None
        try:
            parts = t.split(":")
            hh = int(parts[0])
            mm = int(parts[1]) if len(parts) > 1 else 0
            if not (0 <= hh <= 23 and 0 <= mm <= 59):
                return None
        except Exception:
            return None
        try:
            return System.DateTime(d.Year, d.Month, d.Day, hh, mm, 0)
        except Exception:
            return None

    @staticmethod
    def _pick_output_folder():
        dlg = WinForms.FolderBrowserDialog()
        dlg.Description = "Select the output folder for the scheduled export"
        dlg.ShowNewFolderButton = True
        if dlg.ShowDialog() == WinForms.DialogResult.OK:
            return dlg.SelectedPath
        return None

    # ------------------------------------------------------------------
    # Step 3: View Export
    # ------------------------------------------------------------------
    def _populate_view_source(self, view_rows_data, dwg_version_opts):
        self.view_rows = []
        self._last_view_click_idx = None
        self._view_shift_select_wired = False

        for item in view_rows_data:
            self.view_rows.append(_ViewRow(
                item.get("name", "?"),
                item.get("view_type", ""),
                item.get("is_exportable", True),
                item.get("view", None),
                checked=item.get("is_checked", False),
            ))

        self._all_view_rows = list(self.view_rows)  # kept for search filter
        self.IcViewList.ItemsSource = self.view_rows

        # Check All / Uncheck All (operate on ALL rows, not just filtered)
        self.BtnCheckAllViews.Click   += lambda s, e: self._set_all_views_checked(True)
        self.BtnUncheckAllViews.Click += lambda s, e: self._set_all_views_checked(False)

        # Search bar
        self.TxtViewSearch.TextChanged += self._on_view_search_changed
        self.TxtViewSearchGhost.IsHitTestVisible = False

        # Bubble CheckBox events up to update counter
        try:
            from System.Windows.Controls import CheckBox as _WpfCB
            from System.Windows import RoutedEventHandler as _REH
            self.IcViewList.AddHandler(
                _WpfCB.CheckedEvent,   _REH(lambda s, e: self._update_view_count()))
            self.IcViewList.AddHandler(
                _WpfCB.UncheckedEvent, _REH(lambda s, e: self._update_view_count()))
        except Exception:
            pass

        # Include Views toggle
        self.ChkIncludeViews.IsChecked = False
        self.ChkIncludeViews.Checked   += self._on_include_views_toggled
        self.ChkIncludeViews.Unchecked += self._on_include_views_toggled

        # View format checkboxes — default DWG on
        self.ChkViewDwg.IsChecked  = True
        self.ChkViewPdf.IsChecked  = False
        self.ChkViewPng.IsChecked  = False
        self.ChkViewJpeg.IsChecked = False

        # DWG Version dropdown
        if dwg_version_opts:
            self.CboViewDwgVersion.ItemsSource   = dwg_version_opts
            self.CboViewDwgVersion.SelectedIndex = 0

        # Raster resolution dropdown
        _raster_opts = ["Low (72 DPI)", "Medium (150 DPI)",
                        "High (300 DPI)", "Very High (600 DPI)"]
        self.CboViewResolution.ItemsSource   = _raster_opts
        self.CboViewResolution.SelectedIndex = 2   # High (300 DPI)

        # Pixel size dropdown (PNG / JPEG only)
        _pixel_opts = ["512", "1024", "2048", "4096", "8192"]
        self.CboViewPixelSize.ItemsSource   = _pixel_opts
        self.CboViewPixelSize.SelectedIndex = 2   # default: 2048

        self._update_view_count()

    def _on_view_search_changed(self, sender, args):
        """Filter IcViewList by search text; ghost text visibility."""
        query = (self.TxtViewSearch.Text or "").strip().lower()
        self.TxtViewSearchGhost.Visibility = (
            Visibility.Collapsed if query else Visibility.Visible)
        if query:
            filtered = [r for r in self._all_view_rows
                        if query in r.Name.lower() or query in r.ViewTypeName.lower()]
        else:
            filtered = list(self._all_view_rows)
        self.IcViewList.ItemsSource = filtered
        self.view_rows = filtered
        self._view_shift_select_wired = False   # re-wire shift-select for new containers
        self._update_view_count()

    def _on_include_views_toggled(self, sender, args):
        showing = bool(self.ChkIncludeViews.IsChecked)
        self.SubPanelViewSource.Visibility = (
            Visibility.Visible if showing else Visibility.Collapsed)
        if showing:
            self._update_view_count()
            if not self._view_shift_select_wired:
                self._wire_view_shift_select()

    def _wire_view_shift_select(self):
        """Wire shift-click range-select after WPF has generated containers.
        Uses Dispatcher.BeginInvoke so containers exist when we walk the tree."""
        try:
            from System.Windows.Threading import Dispatcher, DispatcherPriority
            from System.Action import __new__ as _new_action

            def _do_wire():
                try:
                    from System.Windows.Controls import CheckBox as _CB
                    from System.Windows.Input import Keyboard as _KB, ModifierKeys as _MK
                    from System.Windows.Media import VisualTreeHelper as _VTH
                    from System.Windows import RoutedEventHandler as _REH

                    def _make_handler(idx):
                        def _h(s, e):
                            shift = bool(_KB.Modifiers & _MK.Shift)
                            if shift and self._last_view_click_idx is not None:
                                lo = min(idx, self._last_view_click_idx)
                                hi = max(idx, self._last_view_click_idx)
                                target = self.view_rows[self._last_view_click_idx].IsChecked
                                for r in self.view_rows[lo:hi + 1]:
                                    if r.IsExportable:
                                        r.IsChecked = target
                                self.IcViewList.Items.Refresh()
                                e.Handled = True
                                self._update_view_count()
                            else:
                                self._last_view_click_idx = idx
                        return _h

                    gen = self.IcViewList.ItemContainerGenerator

                    def _find_cb(root):
                        from System.Windows.Controls import CheckBox as _CB2
                        from System.Windows.Media import VisualTreeHelper as _VTH2
                        if isinstance(root, _CB2):
                            return root
                        n = _VTH2.GetChildrenCount(root)
                        for ci in range(n):
                            result = _find_cb(_VTH2.GetChild(root, ci))
                            if result is not None:
                                return result
                        return None

                    for i in range(len(self.view_rows)):
                        container = gen.ContainerFromIndex(i)
                        if container is None:
                            continue
                        cb = _find_cb(container)
                        if cb is not None:
                            cb.AddHandler(
                                _CB.PreviewMouseLeftButtonDownEvent,
                                _REH(_make_handler(i)))

                    self._view_shift_select_wired = True
                except Exception:
                    pass

            Dispatcher.CurrentDispatcher.BeginInvoke(
                DispatcherPriority.Loaded,
                _new_action(_do_wire))
        except Exception:
            pass

    def _set_all_views_checked(self, value):
        for r in self._all_view_rows:
            if r.IsExportable:
                r.IsChecked = value
        self.IcViewList.Items.Refresh()
        self._update_view_count()

    def _update_view_count(self):
        total   = len([r for r in self._all_view_rows if r.IsExportable])
        checked = len([r for r in self._all_view_rows if r.IsChecked and r.IsExportable])
        try:
            self.TxtViewCount.Text = "%d of %d views selected" % (checked, total)
        except Exception:
            pass

    def _get_checked_views(self):
        return [r.View for r in self._all_view_rows
                if r.IsChecked and r.IsExportable and r.View is not None]

    def _get_checked_view_formats(self):
        fmts = []
        for attr, label in [("ChkViewDwg", "DWG"), ("ChkViewPdf", "PDF"),
                             ("ChkViewPng", "PNG"), ("ChkViewJpeg", "JPEG")]:
            try:
                if getattr(self, attr).IsChecked:
                    fmts.append(label)
            except Exception:
                pass
        return fmts

    def _build_result_payload(self):
        return {
            "profile_name":     self.profile_name,
            "source_mode":      "selection" if self.RbBySelection.IsChecked else "schedule",
            "schedule_source":  self.CboScheduleSource.SelectedItem,
            "selected_sheets":  self._get_checked_sheet_numbers(),
            "parameters":       [row.Name for row in self.sep_rows],
            "separators":       [row.Separator for row in self.sep_rows],
            "sync_central":     bool(self.ChkSyncCentral.IsChecked),
            "reload_links":     bool(self.ChkReloadLinks.IsChecked),
            "reload_link_names": self._get_checked_link_names() if self.ChkReloadLinks.IsChecked else [],
            "export_formats":   self._get_checked_format_names(),
            "pdf_quality":      self.CboPdfQuality.SelectedItem,
            "pdf_processing":   self.CboPdfProcessing.SelectedItem,
            "dwfx_quality":     self.CboDwfxQuality.SelectedItem,
            "dwf_quality":      self.CboDwfQuality.SelectedItem,
            "compress_pdf":     bool(self.ChkCompressPdf.IsChecked),
            "hide_crop":        bool(self.ChkHideCrop.IsChecked),
            "hide_ref":         bool(self.ChkHideRef.IsChecked),
            "hide_scope":       bool(self.ChkHideScope.IsChecked),
            "hide_view_tags":   bool(self.ChkHideViewTags.IsChecked),
            "dwg_version":      self.CboDwgVersion.SelectedItem,
            "folder_mode":      self.CboFolderMode.SelectedItem if self.CboFolderMode.Visibility == Visibility.Visible else None,
            "include_views":    bool(self.ChkIncludeViews.IsChecked),
            "selected_views":   self._get_checked_views() if self.ChkIncludeViews.IsChecked else [],
            "view_formats":     self._get_checked_view_formats(),
            "view_dwg_version": self.CboViewDwgVersion.SelectedItem,
            "view_resolution":  self.CboViewResolution.SelectedItem or "High (300 DPI)",
            "view_pixel_size":  self.CboViewPixelSize.SelectedItem or "2048",
        }

    def _on_export(self):
        # Ensure separators reflect the final ticked parameter order even if
        # the user never opened Edit Profile in this session (uses whatever
        # was preselected from the loaded profile).
        self.refresh_separators_from_step3()

        _views_only = (bool(self.ChkIncludeViews.IsChecked)
                       and bool(self._get_checked_views())
                       and bool(self._get_checked_view_formats()))

        if self.RbBySelection.IsChecked and not self._get_checked_sheet_numbers():
            if not _views_only:
                MessageBox.Show(
                    "Select at least one sheet on Step 1 (By Selection) before exporting.",
                    "No Sheets Selected",
                    MessageBoxButton.OK, MessageBoxImage.Warning)
                self._show_step(0)
                return   # stay open on the wizard, nothing closes

        if not self._get_checked_format_names():
            if not _views_only:
                MessageBox.Show(
                    "Tick at least one Output Format (PDF, PDF Merge, DWG, DXF, DWFx, or DWF) "
                    "on Step 3 before exporting.",
                    "No Output Format Selected",
                    MessageBoxButton.OK, MessageBoxImage.Warning)
                self._show_step(2)
                return   # stay open on the wizard, nothing closes

        payload = self._build_result_payload()
        payload["schedule_enabled"]   = False
        payload["scheduled_datetime"] = None
        payload["output_folder"]      = None
        payload["include_report"]     = self.schedule_settings.get("include_report", True)

        if self.schedule_settings.get("enabled"):
            sched_dt = self._parse_schedule_datetime()
            if sched_dt is None:
                MessageBox.Show(
                    "Enter a valid Date and Time (HH:mm) in Settings before "
                    "exporting, or disable scheduled export.",
                    "Invalid Schedule",
                    MessageBoxButton.OK, MessageBoxImage.Warning)
                return   # stay open on the wizard, nothing closes

            # Scheduled runs need the output folder chosen up front, since
            # the actual export won't happen until later.
            folder = self._pick_output_folder()
            if not folder:
                return   # user cancelled the folder browser -> back to wizard

            msg = (
                "Export will run automatically at:\n{0}\n\n"
                "Output folder:\n{1}\n\n"
                "Click Proceed to confirm and close this window, or Cancel "
                "to go back and change settings."
            ).format(sched_dt.ToString("dddd, MMMM d, yyyy  HH:mm"), folder)

            answer = MessageBox.Show(
                msg, "Confirm Scheduled Export",
                MessageBoxButton.OKCancel, MessageBoxImage.Question)

            if answer != MessageBoxResult.OK:
                return   # Cancel -> back to the main Export dialog, nothing closes

            payload["schedule_enabled"]   = True
            payload["scheduled_datetime"] = sched_dt
            payload["output_folder"]      = folder

        self.result = payload
        self.Close()