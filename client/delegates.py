import pandas as pd

from . import messages

"""
Injection Methods
"""
class InjectedMethod(object):
    def __init__(self, method_obj) -> None:
        self.method = method_obj

    def __call__(self, *args, **kwds):
        self.method(*args, **kwds)

def inject_methods(delegate, methods: list):
    """
    Method to inject methods into a delegate class

    Parameters:
        delegate_name (str) : identifier for delegate to be modified
        methods (list)  : list of method id's to inject
    """
    state_methods = delegate._client.state["methods"] 
    for id in methods:
        method = state_methods[id[0]]
        # Set attr to the method's info for now - make callable?
        setattr(delegate, method.info.name, method.info)

def inject_signals(delegate, signals: messages.Message):
    state_signals = delegate._client.state["signals"]
    for id in signals:
        signal = state_signals[id[0]]
        setattr(delegate, signal.info.name, signal.info)


"""
Default Delegates for Python Client
"""

class MethodDelegate(object):

    def __init__(self, client):
        self._client = client
        self.info = None

    def on_new(self, message):
        self.info = message

    def on_remove(self, message):
        pass


class SignalDelegate(object):
    
    def __init__(self, client):
        self._client = client
        self.info = None

    def on_new(self, message):
        self.info = message 

    def on_remove(self, message): 
        pass


class SelectionRange(tuple):

    def __new__(cls, key_from, key_to):
        return super().__new__(SelectionRange, (key_from, key_to))


class Selection(object):

    def __init__(self, name: str, rows: list[int] = None, row_ranges: list[SelectionRange] = None) -> None:
        self.name = name
        self.rows = rows
        self.row_ranges = row_ranges

    def __repr__(self) -> str:
        return f"Selection Object({self.__dict__})"

    def __getitem__(self, attribute):
        return getattr(self, attribute)


class TableDelegate(object):
    """
    Delegate class for managing a table

    Attributes:
        _client (Client)        : weak ref to client to invoke methods and such
        dataframe (Dataframe)   : dataframe representing current state of the table
        selections (dict)       : mapping of name to selection object
        signals (signals)       : signals
        name (str)              : name of the table
        id (list)               : id group for delegate in state and table on server

    Methods:
        on_table_init(self, init_info)                      : upon subscribing, create dataframe and update selections
        reset_table(self)                                   : reset table to blank dataframe and clear injected stuff
        insert_rows(self, rows: list)                       : adds rows to end of table
        remove_rows(self, key_list)                         : removes row at each key given
        update_rows(self, keys: list, cols: list)           : updates row at each key, rows passed as series of columns
        update_rows2(self, new_rows: dict)                  : rows passed as dict mapping key to list of row values
        update_cols(self, new_cols: dict)                   : update columns with map of headers to values
        update_selection(self, selection_obj: Selection)    : change or add selection object in state
        get_selection(self, name)                           : get a selection from state 
        relink_signals(self)                                : refresh signal references
        on_new(self, message)                               : handler for create message
        on_update(self, message)                            : handler for update message
        on_remove(self, message)                            : handler for remove message
        subscribe(self, table_id)                           : use id to subscribe to table on server
    """

    def __init__(self, client):
        self._client = client
        self.dataframe = None
        self.name = "Table Delegate"
        self.id = None
        self.selections = {}
        self.signals = {
            "tbl_reset" : self.reset_table,
            "tbl_rows_removed" : self.remove_rows,
            "tbl_updated" : self.update_rows,
            "tbl_selection_updated" : self.update_selection
        }


    def on_table_init(self, init_info):
        """
        Creates table from server response info

        Parameters:
            init_info (Message Obj) : Server response to subscribe
                                      has columns, keys, data, and possibly selections
        """
        # had to set column as just the name - lost type info - ok?
        data_dict = {getattr(col, "name"): data for col, data in zip(
            getattr(init_info, "columns"), getattr(init_info, "data"))}
        self.dataframe = pd.DataFrame(data_dict, index=getattr(init_info, "keys"))

        # Initialize selections if any
        selections = getattr(init_info, "selections", [])
        for selection in selections:
            self.selections[selection.name] = selection
        print(f"Initialized data table...\n{self.dataframe}")


    def reset_table(self):
        """
        Reset dataframe and selections to blank objects
        """
        self.dataframe = pd.DataFrame()
        self.selections = {}
        print("Table Reset...", self.dataframe)


    def insert_rows(self, rows: list):
        """
        Add rows to end of datatable

        Parameters:
            rows (list) : list of row values to be added to list, 
                          assumed to have value for every column
        """
        # Get col headers, and index to start adding at
        headers = self.dataframe.columns.values
        next_index = self.dataframe.index[-1] + 1
        new_index = range(next_index, next_index + len(rows))

        # Construct new datatable and concatenate
        new_df = pd.DataFrame(rows, columns=headers, index=new_index)
        self.dataframe = pd.concat([self.dataframe, new_df])
        print(f"Added rows...\n{self.dataframe}")


    def remove_rows(self, key_list):
        """
        Removes rows from table

        Parameters:
            key_list (list) : list of keys corresponding to rows to be removed
        """
        self.dataframe.drop(index=key_list, inplace=True)
        print(f"Removed Rows: {key_list}...\n", self.dataframe)


    def update_rows(self, keys: list, cols: list):
        """
        Update rows in table

        Parameters:
            keys (list) : list of keys to update
            cols (list) : list of cols containing the values for each new row,
                          should be col for each col in table, and value for each key
        """
        headers = self.dataframe.columns.values
        new_df = pd.DataFrame({col: data for col, data in zip(
            headers, cols)}, index=keys)
        new_df_filled = new_df.combine_first(self.dataframe) # changes order of columns - problem?
        self.dataframe = new_df_filled
    
        print(f"Updated Rows...{keys}\n", self.dataframe)
        

    def update_rows2(self, new_rows: dict):
        """
        Alternative way to update rows taking dict instead of lists

        Parameters:
            new_rows (dict) : mapping key to new row values, should be value for each col
        """
        # Construct backwards dataframe and transpose
        headers = self.dataframe.columns.values
        new_df = pd.DataFrame(new_rows, index=headers).transpose()
        new_df.combine_first(self.dataframe) 
        
        self.dataframe.update(new_df)
        print(f"Updated Rows 2!...{new_rows.keys()}\n", self.dataframe)


    def update_cols(self, new_cols: dict):
        """
        Method for updating values by column

        Parameters:
            new_cols (dict) : mapping headers to column values
        """
        new_df = pd.DataFrame(new_cols)
        self.dataframe.update(new_df)
        print(f"Updated Cols {new_cols.keys()}...\n", self.dataframe)


    def update_selection(self, selection_obj: Selection):
        """
        Change selection in delegate's state to new selection object

        Parameters:
            selection_obj (Selection)   : obj with new selections to replace obj with same name
        """
        self.selections[selection_obj.name] = selection_obj
        print(f"Made selection {selection_obj.name} = {selection_obj}")
        

    def get_selection(self, name):
        """
        Get a selection object from delegate state and construct Dataframe representation

        Parameters:
            name (str) : name of selection object to get
        """
        # Try to retrieve selection object from instance or return blank frame
        try:
            sel_obj = self.selections[name]
        except:
            return pd.DataFrame(columns=self.dataframe.columns)

        frames = []

        # Get rows already in that selection
        if sel_obj.rows:
            frames.append(self.dataframe.loc[sel_obj["rows"]])

        # Uses ranges in object to get other rows
        if sel_obj.row_ranges:
            ranges = sel_obj["row_ranges"]
            for r in ranges:
                frames.append(self.dataframe.loc[r[0]:r[1]-1])

        # Return frames concatenated
        df = pd.concat(frames)
        print(f"Got selection for {sel_obj}\n{df}")
        return df


    def relink_signals(self):
        self.signals["tbl_reset"] = self.reset_table
        self.signals["tbl_rows_removed"] = self.remove_rows
        self.signals["tbl_updated"] = self.update_rows
        self.signals["tbl_selection_updated"] = self.update_selection

    def on_new(self, message: messages.Message):
        
        print("creating a table...")
        # Set name
        self.id = message.id
        name = message["name"]
        methods = message["methods_list"]
        signals = message["signals_list"]
        if name: self.name = name
    
        # Inject methods and signals
        if methods: inject_methods(self, methods)
        if signals: inject_signals(self, signals)

        # Reset
        self.reset_table()
        self.relink_signals()

    def on_update(self, message):
        # delegate updated so need to relink signals incase those methods were overwritten
        self.relink_signals()
        pass

    def on_remove(self, message): 
        pass

    def subscribe(self):
        # what type is table_id, and where to convert?
        invoke_id = messages.InvokeIDType(table=self.id)
        #invoke_id = messages.InvokeIDType.generate({"table": table_id})
        self._client.invoke_method(4, [], context=invoke_id, callback=self.on_table_init)

    def handle_signal(self, signal_data):
        print(signal_data)

class DocumentDelegate(object):
    
    def __init__(self, client):
        self._client = client

    def on_update(self, message):
        pass

    def on_reset(self, message): 
        pass

class EntityDelegate(object):

    def __init__(self, client):
        self._client = client
        self.info = None

    def on_new(self, message):
        self.info = message

    def on_update(self, message):
        pass

    def on_remove(self, message): 
        pass

    def handle_signal(self, signal_data):
        print(signal_data)

class PlotDelegate(object):

    def __init__(self, client):
        self._client = client
        self.info = None

    def on_new(self, message):
        self.info = message

    def on_update(self, message):
        pass

    def on_remove(self, message): 
        pass

    def handle_signal(self, signal_data):
        print(signal_data)

class MaterialDelegate(object):

    def __init__(self, client):
        self._client = client
        self.info = None

    def on_new(self, message):
        self.info = message

    def on_update(self, message):
        pass

    def on_remove(self, message): 
        pass

class GeometryDelegate(object):

    def __init__(self, client):
        self._client = client
        self.info = None

    def on_new(self, message):
        self.info = message

    def on_update(self, message):
        pass

    def on_remove(self, message): 
        pass

class LightDelegate(object):

    def __init__(self, client):
        self._client = client
        self.info = None

    def on_new(self, message):
        self.info = message

    def on_update(self, message):
        pass

    def on_remove(self, message): 
        pass

class ImageDelegate(object):

    def __init__(self, client):
        self._client = client
        self.info = None

    def on_new(self, message):
        self.info = message

    def on_update(self, message):
        pass

    def on_remove(self, message): 
        pass

class TextureDelegate(object):

    def __init__(self, client):
        self._client = client
        self.info = None

    def on_new(self, message):
        self.info = message

    def on_update(self, message):
        pass

    def on_remove(self, message): 
        pass

class SamplerDelegate(object):

    def __init__(self, client):
        self._client = client
        self.info = None

    def on_new(self, message):
        self.info = message

    def on_update(self, message):
        pass

    def on_remove(self, message): 
        pass

class BufferDelegate(object):

    def __init__(self, client):
        self._client = client
        self.info = None

    def on_new(self, message):
        self.info = message

    def on_update(self, message):
        pass

    def on_remove(self, message): 
        pass

class BufferViewDelegate(object):

    def __init__(self, client):
        self._client = client
        self.info = None

    def on_new(self, message):
        self.info = message

    def on_update(self, message):
        pass

    def on_remove(self, message): 
        pass
