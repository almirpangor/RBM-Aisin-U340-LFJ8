package main

import (
	"debug/elf"
	"encoding/binary"
	"fmt"
	"io"
	"os"

	"github.com/user-none/erings/core/sh2"
)

const (
	romStart = 0x1000
	ramStart = 0x10000
	stackTop = 0x12000
	returnPC = 0x20
	maxSteps = 1_000_000
)

type testMemory struct {
	data   [stackTop]byte
	romEnd uint32
}

func (m *testMemory) readAddress(addr, size uint32) []byte {
	if addr >= romStart && addr < m.romEnd && size <= m.romEnd-addr {
		return m.data[addr : addr+size]
	}
	return m.writeAddress(addr, size)
}

func (m *testMemory) writeAddress(addr, size uint32) []byte {
	if addr < ramStart || addr >= stackTop || size > stackTop-addr {
		panic(fmt.Sprintf("unmapped memory access: 0x%08x, width %d", addr, size))
	}
	return m.data[addr : addr+size]
}

func (m *testMemory) Read8(a uint32) uint8       { return m.readAddress(a, 1)[0] }
func (m *testMemory) Read16(a uint32) uint16     { return binary.BigEndian.Uint16(m.readAddress(a, 2)) }
func (m *testMemory) Read32(a uint32) uint32     { return binary.BigEndian.Uint32(m.readAddress(a, 4)) }
func (m *testMemory) Write8(a uint32, v uint8)   { m.writeAddress(a, 1)[0] = v }
func (m *testMemory) Write16(a uint32, v uint16) { binary.BigEndian.PutUint16(m.writeAddress(a, 2), v) }
func (m *testMemory) Write32(a uint32, v uint32) { binary.BigEndian.PutUint32(m.writeAddress(a, 4), v) }

func (m *testMemory) SH2Read8(a uint32, _ int64, _ bool) (uint8, uint32)   { return m.Read8(a), 1 }
func (m *testMemory) SH2Read16(a uint32, _ int64, _ bool) (uint16, uint32) { return m.Read16(a), 1 }
func (m *testMemory) SH2Read32(a uint32, _ int64, _ bool) (uint32, uint32) { return m.Read32(a), 1 }
func (m *testMemory) SH2Write8(a uint32, v uint8, _ int64, _ bool) uint32  { m.Write8(a, v); return 1 }
func (m *testMemory) SH2Write16(a uint32, v uint16, _ int64, _ bool) uint32 {
	m.Write16(a, v)
	return 1
}
func (m *testMemory) SH2Write32(a uint32, v uint32, _ int64, _ bool) uint32 {
	m.Write32(a, v)
	return 1
}

func (*testMemory) AccessCycles(_, _ uint32) uint32         { return 1 }
func (*testMemory) WriteAccessCycles(_, _ uint32) uint32    { return 1 }
func (m *testMemory) ReadCacheLine(a uint32, dst *[16]byte) { copy(dst[:], m.readAddress(a, 16)) }
func (m *testMemory) SH2FillLine(a uint32, dst *[16]byte, _ int64, _ bool) uint32 {
	m.ReadCacheLine(a, dst)
	return 1
}
func (m *testMemory) ReadRMW8(a uint32) uint8                              { return m.Read8(a) }
func (m *testMemory) WriteRMW8(a uint32, v uint8)                          { m.Write8(a, v) }
func (m *testMemory) SH2RMWRead(a uint32, _ int64, _ bool) (uint8, uint32) { return m.ReadRMW8(a), 1 }
func (m *testMemory) SH2RMWWrite(a uint32, v uint8, _ int64) uint32 {
	m.WriteRMW8(a, v)
	return 1
}

func run(path string) error {
	file, err := elf.Open(path)
	if err != nil {
		return err
	}
	defer file.Close()
	if file.Class != elf.ELFCLASS32 || file.Data != elf.ELFDATA2MSB || file.Machine != elf.EM_SH || file.Type != elf.ET_EXEC {
		return fmt.Errorf("expected a linked ELF32 big-endian SuperH self-test")
	}
	memory := &testMemory{}
	for _, prog := range file.Progs {
		if prog.Type != elf.PT_LOAD {
			continue
		}
		if memory.romEnd != 0 || prog.Vaddr != romStart || prog.Memsz != prog.Filesz || prog.Memsz > ramStart-romStart || prog.Flags != elf.PF_R|elf.PF_X {
			return fmt.Errorf("unexpected test load segment: %+v", prog.ProgHeader)
		}
		memory.romEnd = romStart + uint32(prog.Filesz)
		if _, err := io.ReadFull(prog.Open(), memory.data[romStart:memory.romEnd]); err != nil {
			return err
		}
	}
	if file.Entry < romStart || file.Entry >= uint64(memory.romEnd) || file.Entry&1 != 0 {
		return fmt.Errorf("entry 0x%x is outside the test code", file.Entry)
	}
	cpu := sh2.New(memory, true)
	cpu.SetPC(uint32(file.Entry))
	cpu.SetPR(returnPC)
	cpu.SetReg(15, stackTop)
	for r := 8; r <= 14; r++ {
		cpu.SetReg(r, uint32(0x12340000+r))
	}
	lowestSP := uint32(stackTop)
	for n := 0; n < maxSteps; n++ {
		regs := cpu.Registers()
		if regs.R[15] < lowestSP {
			lowestSP = regs.R[15]
		}
		if regs.PC == returnPC {
			if regs.R[15] != stackTop || regs.R[0] != 0 {
				return fmt.Errorf("test returned %d with SP=0x%x after %d steps", regs.R[0], regs.R[15], n)
			}
			for r := 8; r <= 14; r++ {
				if regs.R[r] != uint32(0x12340000+r) {
					return fmt.Errorf("callee-saved r%d was clobbered", r)
				}
			}
			fmt.Printf("PASS SuperH test: %d steps, stack peak %d bytes, restored SP and R8-R14, result %d\n", n, stackTop-lowestSP, regs.R[0])
			return nil
		}
		if regs.PC < romStart || regs.PC >= memory.romEnd || !cpu.Step() {
			return fmt.Errorf("execution left the test code or halted at 0x%x", regs.PC)
		}
	}
	return fmt.Errorf("test has not returned after %d steps", maxSteps)
}

func main() {
	if len(os.Args) != 2 {
		fmt.Fprintln(os.Stderr, "usage: s05check <self-test.elf>")
		os.Exit(2)
	}
	if err := run(os.Args[1]); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
