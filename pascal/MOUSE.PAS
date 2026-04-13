{ ============================================================================ }
{ MOUSE.PAS -- DOS Mouse Driver Interface Unit (INT 33h)                       }
{                                                                              }
{ Provides Pascal wrappers for the standard DOS mouse driver subfunctions:     }
{   init              -- Fn 00h: Initialize mouse driver                       }
{   MouseOn           -- Fn 01h: Show mouse cursor                             }
{   MouseOff          -- Fn 02h: Hide mouse cursor                             }
{   GetMouseInfo      -- Fn 03h: Get position and button state                 }
{   SetMouseXY        -- Fn 04h: Set cursor position                           }
{   GetMouseXYOnDown  -- Fn 05h: Get button press info                         }
{   GetMouseXYOnUp    -- Fn 06h: Get button release info                       }
{   SetXRange         -- Fn 07h: Set horizontal movement range                 }
{   SetYRange         -- Fn 08h: Set vertical movement range                   }
{   SetExeptionRegion -- Fn 10h: Set cursor exclusion rectangle                }
{   SetCursorForm     -- Fn 09h: Set cursor shape in graphics mode             }
{ ============================================================================ }

unit mouse;
interface

{ Fn 00h: Initialize mouse driver. AX=FFFFh means present (ErrorCode=0). }
procedure init (var ButtonCount, ErrorCode : byte);{Initialization}

{ Fn 01h: Show the mouse cursor on screen. }
procedure MouseOn;

{ Fn 02h: Hide the mouse cursor (call before direct screen drawing). }
procedure MouseOff;
procedure GetMouseInfo(var x, y:word; var LeftButton, RightButton, ThirdButton: boolean);
procedure SetMouseXY(x, y : word);
procedure GetMouseXYOnDown(var x, y : word; ButtonNumber: byte;var Count:byte;var LeftButton,RightButton,ThirdButton:boolean);

{ Fn 06h: Get position and count of button releases since last call. }
procedure GetMouseXYOnUp(var x, y:word; ButtonNumber:byte; var Count:byte;var LeftButton, RightButton, ThirdButton:boolean);

{ Fn 07h: Set horizontal range [xmin..xmax] for cursor movement. }
procedure SetXRange (xmin, xmax : word);

{ Fn 08h: Set vertical range [ymin..ymax] for cursor movement. }
procedure SetYRange (ymin, ymax : word);

{ Fn 10h: Define a rectangle where the cursor will not be displayed. }
procedure SetExeptionRegion (X1, Y1, X2, Y2 : word);

{ Fn 09h: Set custom cursor bitmap in graphics mode (AND/XOR mask pair). }
procedure SetCursorForm (xPointer, yPointer: shortint; Form : Pointer);

implementation
uses crt,dos,graph;
var regs:registers;

{ Fn 00h: Initialize mouse driver. AX=FFFFh means present (ErrorCode=0). }
procedure init (var ButtonCount, ErrorCode : byte);
begin
clrscr;
with regs do begin
ax := $0000;
intr($33, regs);
if ax = $FFFF then ErrorCode := 0 else ErrorCode := 1;
ButtonCount :=bx {код числа клавиш 2-2 клавиши, 0 - больше или меньше
чем 2, 3 - мышь системы Mouse Systems (3 клавиши)}
end;
End;

{ Fn 01h: Show the mouse cursor on screen. }
procedure MouseOn;
begin
regs.ax := $0001;
intr($33, regs)
end;

{ Fn 02h: Hide the mouse cursor (call before direct screen drawing). }
procedure MouseOff;
begin
regs.ax := $0002;
intr($33, regs)
end;

{ Fn 03h: Get cursor position and button states (bit 0=left, 1=right, 2=middle). }
procedure GetMouseinfo(var X, Y:word; var LeftButton, RightButton, ThirdButton: boolean);
{возвращает координаты курсора и состояние клавиш,
нажатой кнопке соответствует TRUE, не нажатой - FALSE}
var ButtonCode : byte;
begin
with regs do begin
ax := $0003;
intr($33, regs);
X:=CX;
Y:=DX;
ButtonCode := bx
end;


LeftButton := (ButtonCode and 1) = 1;
RightButton := (ButtonCode and 2) = 2;
ThirdButton := (ButtonCode and 4) = 4
end;

{ Fn 04h: Move the mouse cursor to specified screen coordinates. }
procedure SetMouseXY(x,y : word);

begin
with regs do begin
ax := $0004;
cx := x;
dx := y;
intr($33, regs)
end
end;

{ Fn 05h: Get position and count of button presses since last call. }
procedure GetMouseXYOnDown (var X, Y : word; ButtonNumber: byte;
var Count: byte;var LeftButton, RightButton, ThirdButton: boolean);
{возвращает координаты х, у курсора мыши на момент нажатия клавиши, заданной
кодом ButtonNumber 0 - левая, 1 - правая, 2 - третья;
возвращает LeftButton, RigthButton, ThirdButton - состояние клавиш на данный
момент (нажатой кнопке соответствует TRUE, не нажатой - FALSE);
Count - число нажатий заданной клавиши после последнего вызова
функции GetMouseXYOnDown} var ButtonCode : byte;
begin
with regs do begin
ax := $0005;
bx := ButtonNumber;
intr($33, regs);
ButtonCode := ax;
Count := bx;
X := CX;
y:=dx

end;


LeftButton := (ButtonCode and 1) = 1;
RightButton := (ButtonCode and 2) = 2;
ThirdButton := (ButtonCode and 4) = 4
end;

{ Fn 06h: Get position and count of button releases since last call. }
procedure GetMouseXYOnUp(var x, y:word; ButtonNumber:byte; var Count:byte;var LeftButton, RightButton, ThirdButton:boolean);
 var ButtonCode : byte;
begin
with regs do begin
ax := $0006;
bx := ButtonNumber;
intr($33, regs);
ButtonCode := ax;
Count := bx;
X := CX;
Y := dx
end;

LeftButton := (ButtonCode and 1) = 1;
RightButton := (ButtonCode and 2) = 2;
ThirdButton := (ButtonCode and 4) = 4
end;

{ Fn 07h: Set horizontal range [xmin..xmax] for cursor movement. }
procedure SetXRange (xmin, xmax : word);

begin
with regs do begin
ax := $0007;
Cx := xmin;
 dx := xmax;
intr($33, regs)
end
end;

{ Fn 08h: Set vertical range [ymin..ymax] for cursor movement. }
procedure SetYRange (ymin, ymax : word);

begin
with regs do begin
ax := $0008;
Cx := ymin;
dx := ymax;
intr($33, regs)
end
end;

{ Fn 10h: Define a rectangle where the cursor will not be displayed. }
procedure SetExeptionRegion (X1, Y1, X2, Y2 : word);
{устанавливает прямоугольную область, в которой курсор не отображается, (х1, у1) - координаты верхнего левого,
(х2, у2) - нижнего правого углов}
begin
with regs do begin
ax := $0010;
Cx := X1; dx := Y1;
si :=x2; di :=y2;
intr($33, regs)
    end
end;

{ Fn 09h: Set custom cursor bitmap in graphics mode (AND/XOR mask pair). }
procedure SetCursorForm (xPointer, yPointer: shortint; Form : Pointer);
{установка новой формы курсора в графическом режиме. Form - указатель на область хранения маски;
XPointer, yPointer - координаты горячей точки} begin
MouseOff;                 with regs do begin
ax := $0009;
bx := xPointer;
CX := yPointer;
es := seg(Form^);
dx := ofs(Form^);
intr($33,regs);
MouseOn
end
end;

begin
end.