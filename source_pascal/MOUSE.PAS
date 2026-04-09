unit mouse;
interface
procedure init (var ButtonCount, ErrorCode : byte);{Initialization}
procedure MouseOn;      {включение курсора мыши}
procedure MouseOff;        {выключение курсора мыши}
procedure GetMouseInfo(var x, y:word; var LeftButton, RightButton, ThirdButton: boolean);
procedure SetMouseXY(x, y : word);{установка курсора в заданной точке экрана}
procedure GetMouseXYOnDown(var x, y : word; ButtonNumber: byte;var Count:byte;var LeftButton,RightButton,ThirdButton:boolean);
procedure GetMouseXYOnUp(var x, y:word; ButtonNumber:byte; var Count:byte;var LeftButton, RightButton, ThirdButton:boolean);
procedure SetXRange (xmin, xmax : word);
procedure SetYRange (ymin, ymax : word);
procedure SetExeptionRegion (X1, Y1, X2, Y2 : word);
procedure SetCursorForm (xPointer, yPointer: shortint; Form : Pointer);

implementation
uses crt,dos,graph;
var regs:registers;

{------------------------------}
procedure init (var ButtonCount, ErrorCode : byte);
begin
clrscr;
with regs do begin
ax := $0000;
intr($33, regs);
if ax = $FFFF then ErrorCode := 0 else ErrorCode := 1; {определение ошибки}
ButtonCount :=bx {код числа клавиш 2-2 клавиши, 0 - больше или меньше
чем 2, 3 - мышь системы Mouse Systems (3 клавиши)}
end;
End;
{------------------------------}
procedure MouseOn;      {включение курсора мыши}
begin
regs.ax := $0001;       {задан номер функции}
intr($33, regs)
end;
{------------------------------}
procedure MouseOff;        {выключение курсора мыши}
begin
regs.ax := $0002;          {задан номер функции}
intr($33, regs)
end;
{------------------------------}
procedure GetMouseinfo(var X, Y:word; var LeftButton, RightButton, ThirdButton: boolean);
{возвращает координаты курсора и состояние клавиш,
нажатой кнопке соответствует TRUE, не нажатой - FALSE}
var ButtonCode : byte;                 {код нажатых клавиш}
begin
with regs do begin
ax := $0003;                     {задан номер функции}
intr($33, regs);                   {вызвано прерывание}
X:=CX;                         {получена координата X}
Y:=DX;                         {получена координата Y}
ButtonCode := bx                 {получен код нажатых клавиш}
end;
                       {конец оператора with regs do begin}
{выделение состояния клавиш по отдельным битам ButtonCode}
LeftButton := (ButtonCode and 1) = 1;  {левая кнопка бит 0 в ButtonCode}
RightButton := (ButtonCode and 2) = 2; {правая кнопка бит 1 в ButtonCode}
ThirdButton := (ButtonCode and 4) = 4 {третья кнопка бит 2 в ButtonCode}
end;
{------------------------------}
procedure SetMouseXY(x,y : word);
{установка курсора в заданной точке экрана}
begin
with regs do begin
ax := $0004;    {задан номер функции)}
cx := x;  {задана координата х}
dx := y;        {задана координата у}
intr($33, regs) {вызвано прерывание}
end     {конец оператора with regs do begin}
end;
{------------------------------}
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
ax := $0005;              {задан номер функции}
bx := ButtonNumber;       {задан номер клавиши}
intr($33, regs);             {вызвано прерывание}
ButtonCode := ax;          {получен код нажатых клавиш}
Count := bx;              {получено число нажатий заданной клавиши}
X := CX;                   {получена координата X}
y:=dx                   {получена координата Y}

end;                       {конец оператора with regs do begin}

{выделение состояния клавиш по отдельным битам ButtonCode}
LeftButton := (ButtonCode and 1) = 1;     {левая кнопка бит 0 в ButtonCode}
RightButton := (ButtonCode and 2) = 2;   {правая кнопка бит 1 в ButtonCode}
ThirdButton := (ButtonCode and 4) = 4    {третья кнопка бит 2 в ButtonCode}
end;
{------------------------------}
procedure GetMouseXYOnUp(var x, y:word; ButtonNumber:byte; var Count:byte;var LeftButton, RightButton, ThirdButton:boolean);
{возвращает координаты х, у курсора мыши на момент отпускания клавиши} var ButtonCode : byte;
begin
with regs do begin
ax := $0006;              {задан номер функции}
bx := ButtonNumber;       {задан номер клавиши}
intr($33, regs);            {вызвано прерывание}
ButtonCode := ax;          {получен код нажатых клавиш}
Count := bx;               {получено число нажатий заданной клавиши}
X := CX;                   {получена координата X}
Y := dx                   {получена координата Y}
end;                       {конец оператора with regs do begin}
{выделение состояния клавиш по отдельным битам ButtonCode}
LeftButton := (ButtonCode and 1) = 1;     {левая кнопка бит 0 в ButtonCode}
RightButton := (ButtonCode and 2) = 2;   {правая кнопка бит 1 в ButtonCode}
ThirdButton := (ButtonCode and 4) = 4    {третья кнопка бит 2 в ButtonCode}
end;
{------------------------------}
procedure SetXRange (xmin, xmax : word);
{устанавливает ограничение перемещения курсора мыши по горизонтали}
begin
with regs do begin
ax := $0007;                          {задан номер функции}
Cx := xmin;                           {задана нижняя граница}
 dx := xmax;                           {задана верхняя граница}
intr($33, regs)                        {вызвано прерывание}
end
end;
{------------------------------}
procedure SetYRange (ymin, ymax : word);
{устанавливает ограничение перемещения курсора мыши по вертикали}
begin
with regs do begin
ax := $0008;                          {задан номер функции}
Cx := ymin;                           {задана нижняя граница}
dx := ymax;                          {задана верхняя граница}
intr($33, regs)                        {вызвано прерывание}
end
end;
{------------------------------}
procedure SetExeptionRegion (X1, Y1, X2, Y2 : word);
{устанавливает прямоугольную область, в которой курсор не отображается, (х1, у1) - координаты верхнего левого,
(х2, у2) - нижнего правого углов}
begin
with regs do begin
ax := $0010;                         {задан номер функции}
Cx := X1; dx := Y1;                      {установка координат углов}
si :=x2; di :=y2;
intr($33, regs)                         {вызов прерывания}
    end
end;
{------------------------------}
procedure SetCursorForm (xPointer, yPointer: shortint; Form : Pointer);
{установка новой формы курсора в графическом режиме. Form - указатель на область хранения маски;
XPointer, yPointer - координаты горячей точки} begin
MouseOff;                {выключение курсора перед заменой его формы} with regs do begin
ax := $0009;            {задан номер функции}
bx := xPointer;           {заданы координаты горячей точки}
CX := yPointer;
es := seg(Form^);        {задан сегмент области хранения масок}
dx := ofs(Form^);        {задано смещение области хранения масок}
intr($33,regs);           {вызвано прерывание}
MouseOn              {включение нового курсора}
end
end;

begin
end.