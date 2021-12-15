from ctypes import *
from ctypes.util import find_library
import time
import os
import sys

#Essbase constants
ESS_BYTES_PER_CHARACTER     = 4
ESS_BYTES_FOR_TRAILING_NULL = 5
ESS_TRUE                    = 1

# Change this to to True for Unicode enablement
ESS_UTF                     = False

#MaxL constants
MAXL_OPMODE_DEFAULT         = 0
MAXL_OPMODE_UTF             = 2
MAXL_MSGTEXT_LEN_NATIVE     = 256
MAXL_MSGTEXT_LEN            = ((MAXL_MSGTEXT_LEN_NATIVE * ESS_BYTES_PER_CHARACTER) + ESS_BYTES_FOR_TRAILING_NULL)
MAXL_COLUMN_NAME_LEN_NATIVE = 64
MAXL_COLUMN_NAME_LEN        = ((MAXL_COLUMN_NAME_LEN_NATIVE * ESS_BYTES_PER_CHARACTER) + ESS_BYTES_FOR_TRAILING_NULL)
MAXL_MSGNO_COL_PREP_NUM     = 1241045
MAXL_MDXCELLSTRSZ           = 1024

# Return codes as defined in maxldefs.h
MAXL_MSGLVL_SUCCESS     = 0
MAXL_MSGLVL_WARNING     = 1
MAXL_MSGLVL_ERROR       = 2
MAXL_MSGLVL_SESSION     = 5
MAXL_MSGLVL_FATAL       = 6
MAXL_MSGLVL_END_OF_DATA = 108

# MaxL's internal data types (maxldefs.h)
MAXL_DTINT_BOOL     = 1
MAXL_DTINT_NUMBER   = 2
MAXL_DTINT_CHAR     = 3
MAXL_DTINT_DOUBLE   = 4

# External data types supported by MaxL (maxldefs.h)
MAXL_DTEXT_UCHAR    = 2
MAXL_DTEXT_DOUBLE   = 10
MAXL_DTEXT_STRING   = 11

# MDX column types supported by MaxL (maxldefs.h)
MAXL_MDXINTTYPE     = 0
MAXL_MDXLONGTYPE    = 1
MAXL_MDXULONGTYPE   = 2
MAXL_MDXSHORTTYPE   = 3
MAXL_MDXUSHORTTYPE  = 4
MAXL_MDXFLOATTYPE   = 5
MAXL_MDXSTRTYPE     = 6
MAXL_MDXMEMTYPE     = 7
MAXL_MDXDATASTRTYPE = 8

#Other constants
MAX_REC = 1     # we are going to retrieve one record at a time
MAX_COL = 1024  # maximum column size

ESS_PVOID_T = c_void_p
ESS_PPVOID_T = POINTER(ESS_PVOID_T)

class maxl_instinit_t(Structure):
    _fields_ = [('CtxListLen', c_ushort),
                ('MsgText', (c_char * MAXL_MSGTEXT_LEN)),
                ('MsgTextFill', (c_char * 3)),
                ('bUTFInput', c_ubyte)]

class maxl_ssninit_t(Structure):
    _fields_ = [('MsgLevel', c_ulong),
                ('MsgNumber', c_long),
                ('MsgText', (c_char * MAXL_MSGTEXT_LEN)),
                ('MsgTextFill', (c_char * 3)),
                ('pNewPassword', c_char_p),
                ('ExecElapsedTime', c_ulong),
                ('ExecVerb', c_ulong),
                ('ExecArity', c_ulong),
                ('RowCount', c_ulong),
                ('Card', c_ulong),
                ('pReserved1', c_void_p),
                ('pReserved2', c_void_p),
                ('pReserved3', c_void_p),
                ('pReserved4', c_void_p),
                ('bMdxQuery', c_ulong)]

class maxl_column_descr_t(Structure):
    _fields_ = [('Name', (c_char * MAXL_COLUMN_NAME_LEN)),
                ('NameFill', (c_char * 3)),
                ('IntTyp', c_ulong),
                ('IntLen', c_long),
                ('IntRealLen', c_ulong)]

MAXL_MDXCOLUMNTYPE_T = c_ulong
class maxl_mdxoutputheader_t(Structure):
    _fields_ = [('Type', MAXL_MDXCOLUMNTYPE_T),
                ('sName', (c_char * MAXL_MDXCELLSTRSZ))]

__maxldll = find_library('essmaxlu')
maxl = cdll.LoadLibrary(__maxldll)

class Essbase:
    isInitialized = False
    def __init__(self):
        self.user = None
        self.sid = None
        self.ssnInit = None
        self.numRows = None
        self.numFlds = None
        self.sts = None
        self.bMdxQuery = None

        if not Essbase.isInitialized:
            # Initialize MaxL API
            inst = maxl_instinit_t()

            # memset(InstInit, 0, sizeof(MAXL_INSTINIT_T))
            pinst = (c_char * sizeof(inst)).from_address(addressof(inst))
            pinst.value = '\0' * sizeof(inst)
            if ESS_UTF:
                inst.bUTFInput = ESS_TRUE

            sts = maxl.MaxLInit(byref(inst))
            Essbase.isInitialized = (sts == MAXL_MSGLVL_SUCCESS)

    def __del__(self):
        if Essbase.isInitialized:
            # Terminate MaxL API
            sts = maxl.MaxLTerm()
            Essbase.isInitialized = False

    #---------------------------- connect -----------------------------------#
    #
    # Creates new Essbase Session.
    #
    # Arguments:
    #   User name.  Required.  Character string containing valid Essbase
    #                          user name in whose security domain the new
    #                          session is to be established.
    #   Password.   Required.  Password for the user.
    #   Host name.  Optional.  The computer name hosting the Essbase instance
    #                          of interest.
    #
    def connect(self, user, password, host='localhost'):
        sid = c_ushort(0)
        ssnInit = maxl_ssninit_t()

        sts = maxl.MaxLSessionCreate(c_char_p(host), c_char_p(user), c_char_p(password), byref(ssnInit), byref(sid))

        self.user = user
        self.sid = sid
        self.ssnInit = ssnInit
        self.numFlds = 0
        self.sts = sts
        self.bMdxQuery = 0

    #-------------------------------- do ------------------------------------#
    #
    # Performs a MaxL statement.
    #
    # Arguments:
    #   Statement. Required. A string containing a MaxL statement to be
    #                        passed to the server.
    #
    # Returns (and sets Essbase{STATUS} to):
    #
    #   $MAXL_STATUS {NOERR} if execution was successful.  There are likely
    #      to be informational and feedback massages on the message stack,
    #      which may be obtained with the pop_msg() method below.
    #
    #   $MAXL_STATUS {ERROR} if there was a user error.  The numbers of
    #      the encountered errors, their levels and texts may be obtained
    #      with the pop_msg method below.  Note, that there's likely to
    #      be informational messages on the message stack even in if
    #      execution was successful.  These also may be obtained via the
    #      pop_msg call below.
    #
    def do(self, statement):
        sid, ssnInit = self.sid, self.ssnInit
        if not (sid and ssnInit):
            return MAXL_MSGLVL_SESSION

        # execute the statement command
        if ESS_UTF:
            sts = maxl.MaxLExec(sid, c_char_p(statement), c_ulong(MAXL_OPMODE_UTF))
        else:
            sts = maxl.MaxLExec(sid, c_char_p(statement), c_ulong(MAXL_OPMODE_DEFAULT))
        self.sts = sts
        self.bMdxQuery = self.is_mdx()

        if self.bMdxQuery:
            numFlds = c_long(0)
            numRows = c_long(0)
            sts = maxl.MaxlMDXOutputSize(sid, byref(numFlds), byref(numRows))
            self.sts = sts
            if sts > MAXL_MSGLVL_ERROR:
                self.numFlds = None
                self.numRows = None
            else:
                self.numFlds = int(numFlds.value)
                self.numRows = int(numRows.value)
        else:
            if sts > MAXL_MSGLVL_ERROR:
                self.numFlds = None
            else:
                self.numFlds = self.ssnInit.ExecArity

        return sts

    #---------------------------- pop_msg -----------------------------------#
    #
    # Pops next Essbase or MaxL status message from MaxL message stack.
    #
    # Each invocation of the "do" method above results in a stack of status
    # messages.  This stack is unwound by repeatedly calling this function
    # until it returns nothing.  It's okay for a program to ignore the
    # message stack, or only unwind it partially.  The next call to "do" will
    # clear left-over messages.
    #
    # There is likely to be a number of messages on the stack even after a
    # successful execution.  In most cases, a program will only need
    # to know if the execution of the last "do" was successful, which is
    # indicated by the return value from "do".
    #
    # When the message stack is empty the return list elements are undefined
    # and Essbase{STATUS} is set to $MAXL_STATUS{END_OF_DATA}.
    #
    # Arguments: None
    #
    # Returns: List of form:
    #   (<message_number>, <message_level>, <message_text>)
    #
    def pop_msg(self):
        sid, ssnInit, sts = self.sid, self.ssnInit, self.sts
        if not (sid and ssnInit):
            return None, None, None

        msgno = msglevel = arity = 0
        oldSts = self.sts
        done = False
        getAnotherMessage = True

        while getAnotherMessage:
            msgstr = ''
            if oldSts <= MAXL_MSGLVL_ERROR:
                msgno, msglevel, msgstr, arity = self.ssnInit.MsgNumber, self.ssnInit.MsgLevel, self.ssnInit.MsgText, self.ssnInit.ExecArity
                if not (not arity and msgno == MAXL_MSGNO_COL_PREP_NUM):
                    getAnotherMessage = False
                else:
                    getAnotherMessage = True
            elif oldSts == MAXL_MSGLVL_END_OF_DATA:
                done = True
                getAnotherMessage = False

            if not done:
                sts = maxl.MaxLMessageFetch(sid)
                if getAnotherMessage:
                    msgno = msglevel = arity = 0
                    oldSts = sts

        self.sts = sts
        if sts > MAXL_MSGLVL_ERROR and sts != MAXL_MSGLVL_END_OF_DATA:
            msgno, msglevel, msgstr = None, None, None

        return msgno, msglevel, msgstr

    #------------------------- fetch_desc ------------------------------#
    #
    # Returns reference to list of column names in the output table
    # and a reference to the list of column types in the output table.
    #
    def fetch_desc(self):
        col_names = []
        col_types = []

        sid, numFlds, numRows, bMdxQuery = self.sid, self.numFlds, self.numRows, self.bMdxQuery
        if not sid:
            return MAXL_MSGLVL_SESSION

        if not numFlds:
            return tuple(col_names), tuple(col_types)

        if bMdxQuery:
            pHeader_t = POINTER(maxl_mdxoutputheader_t)
            pHeader = pHeader_t()
            sts = maxl.MaxlMDXOutputDescribe(sid, byref(pHeader))
            if sts < MAXL_MSGLVL_ERROR:
                for index in range(numFlds):
                    col_names.append(pHeader[index].sName)
                    col_types.append(pHeader[index].Type)
        else:
            col_array = maxl_column_descr_t * numFlds
            cols = col_array()
            sts = maxl.MaxLOutputDescribe(sid, c_ulong(1), c_ulong(numFlds), byref(cols))
            if sts < MAXL_MSGLVL_ERROR:
                for index in range(numFlds):
                    col_names.append(cols[index].Name)
                    col_types.append(cols[index].IntTyp)

        return tuple(col_names), tuple(col_types)

    #------------------------- fetch_row ------------------------------#
    #
    # Returns a reference to a row of query results in output table as a
    # list and a reference to the data types of the query result values
    # as a list.
    # Essbase->{STATUS} is set to either $MAXL_STATUS{NOERR}, on
    # success, or $MAXL_STATUS{END_OF_DATA}, if there were no rows to
    # fetch, or $MAXL_STATUS{ERROR} if a user error has occured.
    #
    # A row of record is defined as
    #    { val[0], val[1], ... , val[NUM_OF_FIELDS-1] } }
    # Row numbers are counted cardinally from 0:
    #
    def fetch_row(self):
        row = []
        sid, ssnInit, numFlds, bMdxQuery = self.sid, self.ssnInit, self.numFlds, self.bMdxQuery
        if not (sid and ssnInit):
            return MAXL_MSGLVL_SESSION

        if not numFlds:
            return row

        if bMdxQuery:
            sts, row = self._MaxlMDXOutputNextRecord(sid, numFlds)
        else:
            sts, row = self._MaxlOutputNextRecord(sid, ssnInit, numFlds)

        if sts == MAXL_MSGLVL_END_OF_DATA:
            sts = MAXL_MSGLVL_SUCCESS

        self.sts = sts
        return row

    #----------------------- _MaxlOutputNextRecord --------------------#
    def _MaxlOutputNextRecord(self, sid, ssnInit, numFlds):
        row = []
        pDescr = maxl_column_descr_t()

        descr_array = maxl_column_descr_t * numFlds
        pOutputDescrs = descr_array()

        col_t = c_char * (MAX_COL + 1)

        class output_buffer(Union):
            _fields_ = [('pdVal', c_double * MAX_REC),
                        ('pbVal', c_ubyte * MAX_REC),
                        ('pszVal', col_t * MAX_REC)]

        sts = maxl.MaxLOutputDescribe(sid, c_ulong(1), c_ulong(numFlds), byref(pOutputDescrs))

        if sts < MAXL_MSGLVL_ERROR:
            buffer_array = output_buffer * numFlds
            pOutputArray = buffer_array()

            # memset(pOutputArray, 0, sizeof(pOutputArray))
            ppOutputArray = (c_char * sizeof(pOutputArray)).from_address(addressof(pOutputArray))
            ppOutputArray.value = '\0' * sizeof(pOutputArray)

            for index in range(numFlds):
                pBuffer = pOutputArray[index]
                pDescr = pOutputDescrs[index]

                if pDescr.IntTyp in (MAXL_DTINT_DOUBLE, MAXL_DTINT_NUMBER):
                    pInBuff = pBuffer.pdVal
                    Type = MAXL_DTEXT_DOUBLE
                    Size = 0
                elif pDescr.IntTyp == MAXL_DTINT_BOOL:
                    pInBuff = pBuffer.pbVal
                    Type = MAXL_DTEXT_UCHAR
                    Size = 0
                elif pDescr.IntTyp == MAXL_DTINT_CHAR:
                    pInBuff = pBuffer.pszVal
                    Type = MAXL_DTEXT_STRING
                    Size = MAX_COL+1

                sts = maxl.MaxLColumnDefine(sid, c_ulong(index + 1), pInBuff, c_ushort(Size), c_ulong(Type), c_ushort(MAX_REC), None, None)
                if sts >= MAXL_MSGLVL_ERROR:
                    pOutputDescrs = pOutputArray = None
                    return sts, None

            sts = maxl.MaxLOutputFetch(sid, c_ulong(MAXL_OPMODE_DEFAULT))
            if sts == MAXL_MSGLVL_ERROR or sts == MAXL_MSGLVL_END_OF_DATA:
                return sts, None
            elif sts > MAXL_MSGLVL_ERROR:
                pOutputDescrs = pOutputArray = None
                return sts, None

            for index in range(numFlds):
                pDescr = pOutputDescrs[index]
                pBuffer = pOutputArray[index]
                if pDescr.IntTyp in (MAXL_DTINT_DOUBLE, MAXL_DTINT_NUMBER):
                    row.append(pBuffer.pdVal[0])
                elif pDescr.IntTyp == MAXL_DTINT_BOOL:
                    row.append(pBuffer.pbVal[0])
                elif pDescr.IntTyp == MAXL_DTINT_CHAR:
                    row.append(pBuffer.pszVal[0].value)

        pOutputDescrs = None
        pOutputArray = None
        return sts, row

    #-------------------- _MaxlMDXOutputNextRecord --------------------#
    #
    # Description
    #   Returns pOutput->ulCurRow'th row of output data.
    #
    # Parameters
    #   SessionId- in    - MaxL Session id.
    #   ppRecord - out   - Pointer to the buffer which receives the record
    #                      values.
    #
    # Returns
    #   MAXL_NOERR, MAXL_END_OF_DATA, MAXL_ERROR.

    def _MaxlMDXOutputNextRecord(self, sid, numFlds):
        row = []
        pHeader_t = POINTER(maxl_mdxoutputheader_t)
        pHeader = pHeader_t()

        #ESS_PPVOID_T ppRecord;
        #ppRecord = malloc(sizeof(ESS_PVOID_T) * ulNumCols)
        ppRecordAry = ESS_PVOID_T * numFlds
        ppRecord = ppRecordAry()

        sts = maxl.MaxlMDXOutputNextRecord(sid, ppRecord)
        if sts == MAXL_MSGLVL_SUCCESS:
            sts = maxl.MaxlMDXOutputDescribe(sid, byref(pHeader))
            if sts == MAXL_MSGLVL_SUCCESS:
                for index in range(numFlds):
                    fldType = pHeader[index].Type
                    if fldType in (MAXL_MDXINTTYPE, MAXL_MDXLONGTYPE):
                        row.append(cast(ppRecord[index], POINTER(c_long))[0])
                    elif fldType == MAXL_MDXULONGTYPE:
                        row.append(cast(ppRecord[index], POINTER(c_ulong))[0])
                    elif fldType == MAXL_MDXSHORTTYPE:
                        row.append(cast(ppRecord[index], POINTER(c_short))[0])
                    elif fldType == MAXL_MDXUSHORTTYPE:
                        row.append(cast(ppRecord[index], POINTER(c_ushort))[0])
                    elif fldType in (MAXL_MDXFLOATTYPE, MAXL_MDXMEMTYPE):
                        row.append(cast(ppRecord[index], POINTER(c_double))[0])
                    elif fldType in (MAXL_MDXDATASTRTYPE, MAXL_MDXSTRTYPE):
                        row.append(cast(ppRecord[index], POINTER(c_char_p))[0])
                    else:
                        row.append("")

        return sts, row

    #----------------------------- is_mdx -------------------------------#
    #
    # This function can be called after a call to do() in case different
    # output processing is desired for mdx query output than from
    # MaxL command output
    #
    def is_mdx(self):
        sid, ssnInit, sts = self.sid, self.ssnInit, self.sts
        if not (sid and ssnInit):
            return None

        return ssnInit.bMdxQuery

    #----------------------------- disconnect -------------------------------#
    #
    # Terminates a MaxL session and the associated Essbase session.
    #
    def disconnect(self):
        sid = self.sid
        if not sid:
            return MAXL_MSGLVL_SESSION

        sts = maxl.MaxLSessionDestroy(sid)

        if sts < MAXL_MSGLVL_ERROR:
            self.user = None
            self.sid = None
            self.ssnInit = None
            self.numFlds = None
            self.sts = None

        return sts

    # -------------------------------- rows ----------------------------------#
    #
    # Generator that loops through output returned by Essbase 
    #
    def rows(self, value=None):
        if not self.numFlds:
            raise StopIteration
        else:
            try:
                row = self.fetch_row()
                while row:
                    value = (yield row)
                    row = self.fetch_row()
            except GeneratorExit:
                raise
            except Exception as e:
                value = e

    # --------------------------------- tdf ---------------------------------#
    #
    # Returns a result set in the form of a tab-delimited file.
    #
    def tdf(self):
        # setup the header
        name, dt = self.fetch_desc()
        tbl = "\t".join(name) + "\n"
        line = ['-' * len(column) for column in name]
        tbl = tbl + "\t".join(line) + "\n"

        # now populate the tab-delimited file with data
        for row in self.rows():
            record = []
            idx = 0
            for column in row:
                if dt[idx] == MAXL_DTINT_BOOL:
                    if column == 0:
                        record.append('FALSE')
                    else:
                        record.append('TRUE')
                else:
                    record.append(str(column))
                idx += 1
            tbl = tbl + "\t".join(record) + "\n"

        tbl = tbl + "\n"

        return tbl

    # -------------------------------- msgs ----------------------------------#
    #
    # Returns a message list that resulted from executing a MaxL statement.
    #
    def msgs(self, output=sys.stdout):

        msgno, level, msg = self.pop_msg()

        while msgno:
            # Decode message level
            if level == MAXL_MSGLVL_SUCCESS:
                msglvl = "OK/INFO"
            elif level == MAXL_MSGLVL_WARNING:
                msglvl = "WARNING"
            elif level == MAXL_MSGLVL_ERROR:
                msglvl = "ERROR"
            elif level == MAXL_MSGLVL_FATAL:
                msglvl = "FATAL"
            else:
                msglvl = str(level)
            print("%8s - %7d - %s." % (msglvl, msgno, msg), file=output)
            msgno, level, msg = self.pop_msg()

        print('', file=output)

    # ------------------------------- execute -------------------------------#
    #
    # Execute a MaxL statement and print resulting output.
    #
    def execute(self, stmt, output=sys.stdout, timefmt=None):
        # format MaxL statement for output
        stmt = stmt.replace("\t", "")
        out = stmt.split("\n")
        for i in range(1, len(out)):
            out[i] = "%4d> %s" % (i, out[i])
        if timefmt:
            timestamp = time.strftime(timefmt)
        else:
            timestamp = time.asctime()
        print(timestamp, file=output)
        print("MAXL> %s;\n" % "\n".join(out), file=output)

        # execute MaxL statement
        sts = self.do(stmt)

        # exit if the execution failed
        if sts:
            # dump status messages
            self.msgs(output)

            print("Execution of [%s] failed with status %d" % (stmt, sts), file=output)
        elif self.numFlds:
            print(self.tdf(), file=output)

        # dump status messages
        self.msgs(output)

        return sts

